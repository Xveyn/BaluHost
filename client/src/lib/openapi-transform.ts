import { createElement } from 'react';
import { HelpCircle } from 'lucide-react';
import type { ApiEndpoint, ApiSection } from '../data/api-endpoints/types';
import type { TagConfig } from '../data/api-endpoints/tag-mapping';
import { tagMapping, categoryLabels, categoryOrder } from '../data/api-endpoints/tag-mapping';

export interface ApiCategory {
  id: string;
  label: string;
  sections: ApiSection[];
}

// ---------- OpenAPI types (minimal subset) ----------

interface OpenApiSchema {
  paths: Record<string, Record<string, OpenApiOperation>>;
  components?: { schemas?: Record<string, OpenApiSchemaObject> };
}

interface OpenApiOperation {
  tags?: string[];
  summary?: string;
  operationId?: string;
  parameters?: OpenApiParameter[];
  requestBody?: {
    required?: boolean;
    content?: Record<string, { schema?: OpenApiSchemaObject }>;
  };
  responses?: Record<string, {
    content?: Record<string, { schema?: OpenApiSchemaObject }>;
  }>;
  security?: Record<string, string[]>[];
}

interface OpenApiParameter {
  name: string;
  in: string;
  required?: boolean;
  description?: string;
  schema?: OpenApiSchemaObject;
}

interface OpenApiSchemaObject {
  type?: string;
  $ref?: string;
  properties?: Record<string, OpenApiSchemaObject>;
  required?: string[];
  items?: OpenApiSchemaObject;
  allOf?: OpenApiSchemaObject[];
  anyOf?: OpenApiSchemaObject[];
  oneOf?: OpenApiSchemaObject[];
  enum?: (string | number)[];
  title?: string;
  description?: string;
  default?: unknown;
  format?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  example?: any;
}

// ---------- Helpers ----------

const HTTP_METHODS = ['get', 'post', 'put', 'delete', 'patch'] as const;

function resolveRef(ref: string, schemas: Record<string, OpenApiSchemaObject>): OpenApiSchemaObject | undefined {
  // "#/components/schemas/Foo" -> "Foo"
  const name = ref.split('/').pop();
  return name ? schemas[name] : undefined;
}

function resolveSchema(schema: OpenApiSchemaObject, schemas: Record<string, OpenApiSchemaObject>): OpenApiSchemaObject {
  if (schema.$ref) {
    return resolveRef(schema.$ref, schemas) ?? schema;
  }
  if (schema.allOf) {
    // Merge all allOf schemas
    const merged: OpenApiSchemaObject = { type: 'object', properties: {}, required: [] };
    for (const sub of schema.allOf) {
      const resolved = resolveSchema(sub, schemas);
      if (resolved.properties) {
        merged.properties = { ...merged.properties, ...resolved.properties };
      }
      if (resolved.required) {
        merged.required = [...(merged.required ?? []), ...resolved.required];
      }
    }
    return merged;
  }
  if (schema.anyOf || schema.oneOf) {
    const variants = schema.anyOf ?? schema.oneOf ?? [];
    // Filter out null type and use first real variant
    const real = variants.find(v => !v.$ref?.endsWith('NoneType') && v.type !== 'null');
    return real ? resolveSchema(real, schemas) : schema;
  }
  return schema;
}

function schemaTypeLabel(schema: OpenApiSchemaObject, schemas: Record<string, OpenApiSchemaObject>): string {
  const resolved = resolveSchema(schema, schemas);
  if (resolved.enum) return resolved.enum.map(String).join(' | ');
  if (resolved.type === 'array') {
    const itemType = resolved.items ? schemaTypeLabel(resolved.items, schemas) : 'any';
    return `${itemType}[]`;
  }
  if (resolved.$ref) {
    const name = resolved.$ref.split('/').pop();
    return name ?? 'object';
  }
  return resolved.type ?? 'any';
}

function generateExample(schema: OpenApiSchemaObject, schemas: Record<string, OpenApiSchemaObject>, depth = 0): unknown {
  if (depth > 3) return '...';

  if (schema.example !== undefined) return schema.example;

  const resolved = resolveSchema(schema, schemas);
  if (resolved.example !== undefined) return resolved.example;

  if (resolved.enum) return resolved.enum[0];

  switch (resolved.type) {
    case 'string':
      if (resolved.format === 'date-time') return '2026-01-01T00:00:00Z';
      if (resolved.format === 'email') return 'user@example.com';
      if (resolved.format === 'uri' || resolved.format === 'url') return 'https://example.com';
      return 'string';
    case 'integer':
    case 'number':
      return resolved.default !== undefined ? resolved.default : 0;
    case 'boolean':
      return resolved.default !== undefined ? resolved.default : true;
    case 'array': {
      if (!resolved.items) return [];
      const item = generateExample(resolved.items, schemas, depth + 1);
      return [item];
    }
    case 'object':
    case undefined: {
      if (!resolved.properties) {
        // Check if it's a ref that resolved to something with properties
        if (resolved.$ref) {
          const inner = resolveRef(resolved.$ref, schemas);
          if (inner) return generateExample(inner, schemas, depth + 1);
        }
        return {};
      }
      const obj: Record<string, unknown> = {};
      for (const [key, propSchema] of Object.entries(resolved.properties)) {
        obj[key] = generateExample(propSchema, schemas, depth + 1);
      }
      return obj;
    }
    default:
      return null;
  }
}

function extractBodyFields(
  requestBody: OpenApiOperation['requestBody'],
  schemas: Record<string, OpenApiSchemaObject>,
): ApiEndpoint['body'] {
  const content = requestBody?.content?.['application/json']?.schema
    ?? requestBody?.content?.['multipart/form-data']?.schema;
  if (!content) return undefined;

  const resolved = resolveSchema(content, schemas);
  if (!resolved.properties) return undefined;

  const requiredSet = new Set(resolved.required ?? []);
  return Object.entries(resolved.properties).map(([field, propSchema]) => {
    const prop = resolveSchema(propSchema, schemas);
    return {
      field,
      type: schemaTypeLabel(propSchema, schemas),
      required: requiredSet.has(field),
      description: prop.description ?? prop.title ?? '',
    };
  });
}

function extractParams(parameters: OpenApiParameter[] | undefined, schemas: Record<string, OpenApiSchemaObject>): ApiEndpoint['params'] {
  if (!parameters || parameters.length === 0) return undefined;
  return parameters
    .filter(p => p.in === 'query' || p.in === 'path')
    .map(p => ({
      name: p.name,
      type: p.schema ? schemaTypeLabel(p.schema, schemas) : 'string',
      required: p.required ?? false,
      description: p.description ?? '',
    }));
}

function generateResponseExample(
  responses: OpenApiOperation['responses'],
  schemas: Record<string, OpenApiSchemaObject>,
): string | undefined {
  if (!responses) return undefined;
  // Try 200, 201, then first 2xx
  const successKey = ['200', '201'].find(k => responses[k]?.content?.['application/json']?.schema)
    ?? Object.keys(responses).find(k => k.startsWith('2') && responses[k]?.content?.['application/json']?.schema);
  if (!successKey) return undefined;

  const schema = responses[successKey]?.content?.['application/json']?.schema;
  if (!schema) return undefined;

  const example = generateExample(schema, schemas);
  try {
    return JSON.stringify(example, null, 2);
  } catch {
    return undefined;
  }
}

function hasAuth(operation: OpenApiOperation, globalSecurity?: Record<string, string[]>[]): boolean {
  // Per-operation security overrides global
  if (operation.security !== undefined) {
    return operation.security.length > 0;
  }
  // Fall back to global security
  return (globalSecurity?.length ?? 0) > 0;
}

// ---------- Main transform ----------

export function transformOpenApi(schema: OpenApiSchema): { sections: ApiSection[]; categories: ApiCategory[] } {
  const schemas = schema.components?.schemas ?? {};
  const globalSecurity = (schema as { security?: Record<string, string[]>[] }).security;

  // Group endpoints by tag
  const tagEndpoints = new Map<string, ApiEndpoint[]>();

  for (const [path, methods] of Object.entries(schema.paths)) {
    for (const method of HTTP_METHODS) {
      const operation = methods[method];
      if (!operation) continue;

      const tag = operation.tags?.[0] ?? 'other';

      const endpoint: ApiEndpoint = {
        method: method.toUpperCase() as ApiEndpoint['method'],
        path,
        description: operation.summary ?? operation.operationId ?? path,
        requiresAuth: hasAuth(operation, globalSecurity),
        params: extractParams(operation.parameters, schemas),
        body: extractBodyFields(operation.requestBody, schemas),
        response: generateResponseExample(operation.responses, schemas),
      };

      if (!tagEndpoints.has(tag)) tagEndpoints.set(tag, []);
      tagEndpoints.get(tag)!.push(endpoint);
    }
  }

  // Build sections from tags
  const fallbackIcon = createElement(HelpCircle, { className: 'w-5 h-5' });
  const sectionMap = new Map<string, ApiSection>();

  for (const [tag, endpoints] of tagEndpoints) {
    const config: TagConfig = tagMapping[tag] ?? { category: 'other', title: tag, icon: fallbackIcon };
    const key = config.title;

    if (sectionMap.has(key)) {
      // Merge endpoints into existing section (e.g. multiple tags map to same title)
      sectionMap.get(key)!.endpoints.push(...endpoints);
    } else {
      sectionMap.set(key, { title: config.title, icon: config.icon, endpoints });
    }
  }

  const allSections = Array.from(sectionMap.values());

  // Build categories
  const categoryMap = new Map<string, ApiSection[]>();
  for (const [tag] of tagEndpoints) {
    const config = tagMapping[tag] ?? { category: 'other', title: tag, icon: fallbackIcon };
    const section = sectionMap.get(config.title);
    if (!section) continue;

    if (!categoryMap.has(config.category)) categoryMap.set(config.category, []);
    const arr = categoryMap.get(config.category)!;
    if (!arr.includes(section)) arr.push(section);
  }

  const categories: ApiCategory[] = categoryOrder
    .filter(id => categoryMap.has(id))
    .map(id => ({
      id,
      label: categoryLabels[id] ?? id,
      sections: categoryMap.get(id)!,
    }));

  return { sections: allSections, categories };
}
