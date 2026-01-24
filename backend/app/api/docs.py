"""Custom Swagger UI with BaluHost styling."""

from fastapi.openapi.docs import get_swagger_ui_html
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

CUSTOM_CSS = """
/* BaluHost Custom Swagger UI Styling - Matching Frontend Design */
:root {
    --baluhost-bg-primary: #0f172a;
    --baluhost-bg-secondary: #1e293b;
    --baluhost-bg-card: rgba(15, 23, 42, 0.55);
    --baluhost-border: rgba(148, 163, 184, 0.15);
    --baluhost-text: #e2e8f0;
    --baluhost-text-secondary: #94a3b8;
    --baluhost-primary: #3b82f6;
    --baluhost-primary-hover: #60a5fa;
    --baluhost-success: #10b981;
    --baluhost-warning: #f59e0b;
    --baluhost-error: #ef4444;
    --baluhost-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 25%, #1e293b 50%, #0c0a1f 75%, #020617 100%);
}

body {
    background: var(--baluhost-gradient) !important;
    background-attachment: fixed !important;
    color: var(--baluhost-text) !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif !important;
}

/* Topbar */
.swagger-ui .topbar {
    background: var(--baluhost-bg-card) !important;
    border-bottom: 1px solid var(--baluhost-border) !important;
    border-radius: 16px !important;
    backdrop-filter: blur(20px) !important;
    padding: 16px 0 !important;
    margin: 20px 0 !important;
    box-shadow: 0 20px 60px rgba(2, 6, 23, 0.55) !important;
}

.swagger-ui .topbar .wrapper {
    padding: 0 20px !important;
}

.swagger-ui .topbar .download-url-wrapper {
    display: none !important;
}

/* Info Section */
.swagger-ui .info {
    margin: 30px 0 !important;
    background: transparent !important;
}

.swagger-ui .info .title {
    color: var(--baluhost-text) !important;
    font-size: 2.5em !important;
    font-weight: 700 !important;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
}

.swagger-ui .info .description {
    color: var(--baluhost-text-secondary) !important;
    font-size: 1.1em !important;
}

/* Remove white background sections */
.swagger-ui .scheme-container {
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
}

.swagger-ui .wrapper {
    background: transparent !important;
}

.swagger-ui section.models {
    background: transparent !important;
    border: none !important;
}

/* Operation blocks */
.swagger-ui .opblock-tag {
    background: transparent !important;
    border: none !important;
    margin: 0 0 24px 0 !important;
}

.swagger-ui .opblock-tag-section {
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    margin-bottom: 16px !important;
}

.swagger-ui .opblock-tag-section h3 {
    color: var(--baluhost-text) !important;
    font-size: 1.75em !important;
    font-weight: 700 !important;
    margin: 0 !important;
}

.swagger-ui .opblock {
    background: var(--baluhost-bg-card) !important;
    border: 1px solid var(--baluhost-border) !important;
    border-radius: 16px !important;
    margin: 12px 0 !important;
    overflow: hidden !important;
    box-shadow: 0 20px 60px rgba(2, 6, 23, 0.55) !important;
    backdrop-filter: blur(20px) !important;
    transition: all 0.2s !important;
}

.swagger-ui .opblock:hover {
    border-color: rgba(148, 163, 184, 0.3) !important;
    box-shadow: 0 24px 70px rgba(2, 6, 23, 0.65) !important;
}

/* HTTP Method colors - Matching Frontend */
.swagger-ui .opblock.opblock-get {
    border-color: rgba(59, 130, 246, 0.3) !important;
}

.swagger-ui .opblock.opblock-get .opblock-summary-method {
    background: rgba(59, 130, 246, 0.1) !important;
    border: 1px solid rgba(59, 130, 246, 0.5) !important;
    color: #60a5fa !important;
}

.swagger-ui .opblock.opblock-post {
    border-color: rgba(16, 185, 129, 0.3) !important;
}

.swagger-ui .opblock.opblock-post .opblock-summary-method {
    background: rgba(16, 185, 129, 0.1) !important;
    border: 1px solid rgba(16, 185, 129, 0.5) !important;
    color: #34d399 !important;
}

.swagger-ui .opblock.opblock-put,
.swagger-ui .opblock.opblock-patch {
    border-color: rgba(245, 158, 11, 0.3) !important;
}

.swagger-ui .opblock.opblock-put .opblock-summary-method,
.swagger-ui .opblock.opblock-patch .opblock-summary-method {
    background: rgba(245, 158, 11, 0.1) !important;
    border: 1px solid rgba(245, 158, 11, 0.5) !important;
    color: #fbbf24 !important;
}

.swagger-ui .opblock.opblock-delete {
    border-color: rgba(239, 68, 68, 0.3) !important;
}

.swagger-ui .opblock.opblock-delete .opblock-summary-method {
    background: rgba(239, 68, 68, 0.1) !important;
    border: 1px solid rgba(239, 68, 68, 0.5) !important;
    color: #f87171 !important;
}

.swagger-ui .opblock-summary-method {
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    padding: 6px 12px !important;
    min-width: 70px !important;
    text-align: center !important;
    letter-spacing: 0.5px !important;
}

.swagger-ui .opblock-summary-path {
    color: var(--baluhost-text) !important;
    font-family: 'Courier New', monospace !important;
    font-weight: 500 !important;
}

.swagger-ui .opblock-summary-description {
    color: var(--baluhost-text-secondary) !important;
}

/* Buttons - Matching Frontend btn-primary */
.swagger-ui .btn {
    background: linear-gradient(to right, #0ea5e9, #6366f1, #8b5cf6) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 10px 20px !important;
    font-weight: 600 !important;
    transition: all 0.2s !important;
    box-shadow: 0 18px 45px rgba(56, 189, 248, 0.35) !important;
}

.swagger-ui .btn:hover {
    box-shadow: 0 22px 55px rgba(76, 29, 149, 0.45) !important;
    transform: translateY(-2px) !important;
}

.swagger-ui .btn.execute {
    background: linear-gradient(to right, #0ea5e9, #6366f1, #8b5cf6) !important;
    box-shadow: 0 18px 45px rgba(56, 189, 248, 0.4) !important;
}

.swagger-ui .btn.cancel {
    background: rgba(15, 23, 42, 0.7) !important;
    border: 1px solid rgba(148, 163, 184, 0.3) !important;
    box-shadow: 0 10px 35px rgba(15, 23, 42, 0.35) !important;
}

.swagger-ui .btn.cancel:hover {
    border-color: rgba(148, 163, 184, 0.5) !important;
    transform: translateY(-1px) !important;
}

/* Parameters & Request body */
.swagger-ui .opblock-section-header {
    background: rgba(15, 23, 42, 0.6) !important;
    border-radius: 8px !important;
    padding: 12px 16px !important;
    margin-bottom: 12px !important;
}

.swagger-ui .opblock-section-header h4 {
    color: var(--baluhost-text) !important;
    font-weight: 600 !important;
    margin: 0 !important;
}

.swagger-ui .opblock-body {
    background: transparent !important;
    padding: 20px !important;
}

.swagger-ui .parameters-col_description {
    color: var(--baluhost-text-secondary) !important;
}

.swagger-ui .parameter__name {
    color: var(--baluhost-text) !important;
    font-weight: 600 !important;
}

.swagger-ui .parameter__type {
    color: var(--baluhost-primary) !important;
    font-weight: 500 !important;
}

.swagger-ui table {
    background: transparent !important;
    border: none !important;
}

.swagger-ui table thead tr th {
    color: var(--baluhost-text) !important;
    background: rgba(15, 23, 42, 0.4) !important;
    border-bottom: 2px solid var(--baluhost-border) !important;
    padding: 12px 16px !important;
    font-weight: 600 !important;
}

.swagger-ui table tbody tr td {
    color: var(--baluhost-text-secondary) !important;
    border-bottom: 1px solid var(--baluhost-border) !important;
    background: transparent !important;
    padding: 12px 16px !important;
}

.swagger-ui table tbody tr {
    background: transparent !important;
}

.swagger-ui table tbody tr:hover td {
    background: rgba(15, 23, 42, 0.3) !important;
}

/* Code blocks - Matching Frontend pre styling */
.swagger-ui .highlight-code,
.swagger-ui .microlight {
    background: rgba(2, 6, 23, 0.6) !important;
    border: 1px solid rgba(148, 163, 184, 0.2) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    font-family: 'Courier New', Consolas, Monaco, monospace !important;
}

.swagger-ui .response-col_status {
    color: var(--baluhost-text) !important;
    font-weight: 600 !important;
}

/* Models / Schemas */
.swagger-ui .model-container {
    background: transparent !important;
    margin: 20px 0 !important;
}

.swagger-ui .models {
    background: transparent !important;
    border: none !important;
}

.swagger-ui section.models h4 {
    color: var(--baluhost-text) !important;
    font-size: 1.75em !important;
    font-weight: 700 !important;
    margin-bottom: 20px !important;
    border-bottom: 2px solid var(--baluhost-border) !important;
    padding-bottom: 12px !important;
}

.swagger-ui .model-box {
    background: var(--baluhost-bg-card) !important;
    border: 1px solid var(--baluhost-border) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    margin: 10px 0 !important;
    backdrop-filter: blur(20px) !important;
    box-shadow: 0 10px 40px rgba(2, 6, 23, 0.4) !important;
}

.swagger-ui .model-box:hover {
    border-color: rgba(148, 163, 184, 0.3) !important;
    box-shadow: 0 12px 50px rgba(2, 6, 23, 0.5) !important;
}

.swagger-ui .model-title {
    color: var(--baluhost-text) !important;
    font-weight: 700 !important;
    font-size: 1.1em !important;
    margin-bottom: 8px !important;
}

.swagger-ui .model {
    color: var(--baluhost-text-secondary) !important;
}

.swagger-ui .model-toggle {
    color: var(--baluhost-text) !important;
}

.swagger-ui .model-toggle::after {
    background: url('data:image/svg+xml;charset=utf-8,<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="%2394a3b8" d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>') center center no-repeat !important;
}

.swagger-ui .prop-type {
    color: #60a5fa !important;
    font-weight: 600 !important;
}

.swagger-ui .prop-format {
    color: var(--baluhost-text-secondary) !important;
}

.swagger-ui .property-row {
    border-bottom: 1px solid var(--baluhost-border) !important;
}

.swagger-ui .model .property {
    color: var(--baluhost-text) !important;
}

.swagger-ui span.model-toggle {
    padding: 6px 8px !important;
    border-radius: 6px !important;
    transition: background 0.2s !important;
}

.swagger-ui span.model-toggle:hover {
    background: rgba(59, 130, 246, 0.1) !important;
}

/* Schema badges */
.swagger-ui .model-box .model-title span {
    background: rgba(59, 130, 246, 0.15) !important;
    border: 1px solid rgba(59, 130, 246, 0.4) !important;
    color: #60a5fa !important;
    padding: 4px 8px !important;
    border-radius: 6px !important;
    font-size: 0.75em !important;
    font-weight: 600 !important;
    margin-left: 8px !important;
}

/* Schema expanded content */
.swagger-ui .model-box-control {
    background: transparent !important;
}

.swagger-ui .model table {
    background: transparent !important;
    margin: 12px 0 !important;
}

.swagger-ui .model table tr {
    background: transparent !important;
    border-bottom: 1px solid var(--baluhost-border) !important;
}

.swagger-ui .model table tr:hover {
    background: rgba(59, 130, 246, 0.05) !important;
}

.swagger-ui .model table td {
    padding: 12px 8px !important;
    color: var(--baluhost-text-secondary) !important;
    background: transparent !important;
    border: none !important;
}

.swagger-ui .model table td:first-child {
    color: var(--baluhost-text) !important;
    font-weight: 600 !important;
}

.swagger-ui .model .property.primitive {
    color: #60a5fa !important;
}

.swagger-ui .model .property {
    color: var(--baluhost-text) !important;
}

.swagger-ui .model .brace-close {
    color: var(--baluhost-text-secondary) !important;
}

.swagger-ui .model .brace-open {
    color: var(--baluhost-text-secondary) !important;
}

/* Schema property names */
.swagger-ui .model .property-name {
    color: #a78bfa !important;
    font-weight: 500 !important;
}

/* Required badge */
.swagger-ui .model .star {
    color: #ef4444 !important;
}

/* Schema description */
.swagger-ui .model .description {
    color: var(--baluhost-text-secondary) !important;
    margin-top: 8px !important;
}

/* Collapsible model box */
.swagger-ui .model-box .model {
    padding: 0 !important;
}

.swagger-ui .renderedMarkdown p {
    color: var(--baluhost-text-secondary) !important;
}

/* Authorize dialog */
.swagger-ui .dialog-ux {
    background: var(--baluhost-bg-card) !important;
    border: 1px solid var(--baluhost-border) !important;
    border-radius: 16px !important;
    backdrop-filter: blur(20px) !important;
    box-shadow: 0 20px 60px rgba(2, 6, 23, 0.7) !important;
}

.swagger-ui .modal-ux {
    background: rgba(0, 0, 0, 0.8) !important;
    backdrop-filter: blur(4px) !important;
}

.swagger-ui .modal-ux-header {
    background: transparent !important;
    border-bottom: 1px solid var(--baluhost-border) !important;
    padding: 20px !important;
}

.swagger-ui .modal-ux-header h3 {
    color: var(--baluhost-text) !important;
    font-weight: 600 !important;
}

.swagger-ui .modal-ux-content {
    padding: 20px !important;
}

.swagger-ui .auth-container {
    background: transparent !important;
    border: none !important;
}

.swagger-ui .auth-container input[type="text"],
.swagger-ui .auth-container input[type="password"] {
    background: var(--baluhost-bg-secondary) !important;
    border: 1px solid var(--baluhost-border) !important;
    border-radius: 8px !important;
    color: var(--baluhost-text) !important;
    padding: 10px !important;
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}

::-webkit-scrollbar-track {
    background: var(--baluhost-bg-primary);
}

::-webkit-scrollbar-thumb {
    background: var(--baluhost-bg-secondary);
    border-radius: 5px;
    border: 2px solid var(--baluhost-bg-primary);
}

::-webkit-scrollbar-thumb:hover {
    background: var(--baluhost-primary);
}

/* Try it out section */
.swagger-ui .try-out {
    background: transparent !important;
}

.swagger-ui .try-out__btn {
    background: var(--baluhost-primary) !important;
    border: none !important;
    border-radius: 6px !important;
    color: white !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
}

/* Responses */
.swagger-ui .responses-inner {
    background: transparent !important;
}

.swagger-ui .response .response-col_status {
    font-weight: 600 !important;
}

.swagger-ui .response.default {
    border-color: var(--baluhost-border) !important;
}

/* Input fields */
.swagger-ui input[type="text"],
.swagger-ui input[type="password"],
.swagger-ui textarea,
.swagger-ui select {
    background: rgba(15, 23, 42, 0.6) !important;
    border: 1px solid var(--baluhost-border) !important;
    border-radius: 8px !important;
    color: var(--baluhost-text) !important;
    padding: 10px 14px !important;
    transition: all 0.2s !important;
}

.swagger-ui input[type="text"]:focus,
.swagger-ui input[type="password"]:focus,
.swagger-ui textarea:focus,
.swagger-ui select:focus {
    border-color: rgba(59, 130, 246, 0.6) !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;
    background: rgba(15, 23, 42, 0.8) !important;
}

/* Loading indicator */
.swagger-ui .loading-container {
    background: var(--baluhost-bg-card) !important;
}

/* Links */
.swagger-ui a {
    color: var(--baluhost-primary) !important;
    text-decoration: none !important;
}

.swagger-ui a:hover {
    color: var(--baluhost-primary-hover) !important;
    text-decoration: underline !important;
}

/* Wrapper */
.swagger-ui .wrapper {
    max-width: 1400px !important;
    margin: 0 auto !important;
    padding: 0 20px 40px !important;
}

/* Try it out section */
.swagger-ui .try-out {
    background: transparent !important;
}

.swagger-ui .try-out__btn {
    background: linear-gradient(to right, #0ea5e9, #6366f1) !important;
    border: none !important;
    border-radius: 8px !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 8px 16px !important;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
    transition: all 0.2s !important;
}

.swagger-ui .try-out__btn:hover {
    box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4) !important;
    transform: translateY(-1px) !important;
}

/* Execute section */
.swagger-ui .execute-wrapper {
    background: transparent !important;
    padding: 20px 0 !important;
}

/* Response section */
.swagger-ui .responses-wrapper {
    margin-top: 20px !important;
    background: transparent !important;
}

.swagger-ui .responses-inner {
    background: transparent !important;
    padding: 0 !important;
}

.swagger-ui .response {
    background: transparent !important;
    border: none !important;
}

.swagger-ui .response-col_status {
    font-weight: 700 !important;
    color: var(--baluhost-text) !important;
}

.swagger-ui .response-col_description {
    color: var(--baluhost-text-secondary) !important;
}

.swagger-ui .response .response-col_description__inner {
    background: transparent !important;
}

/* Tables */
.swagger-ui table {
    background: transparent !important;
}

.swagger-ui table thead tr th {
    padding: 12px 16px !important;
    font-weight: 600 !important;
}

.swagger-ui table tbody tr td {
    padding: 12px 16px !important;
}

/* Custom BaluHost branding */
.swagger-ui .info .title::before {
    content: "🏠 ";
    font-size: 0.9em;
    margin-right: 8px;
}

/* Authorization button in topbar */
.swagger-ui .topbar .wrapper .authorize {
    background: linear-gradient(to right, #0ea5e9, #6366f1, #8b5cf6) !important;
    border: none !important;
    border-radius: 12px !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
    box-shadow: 0 18px 45px rgba(56, 189, 248, 0.35) !important;
}

.swagger-ui .topbar .wrapper .authorize:hover {
    box-shadow: 0 22px 55px rgba(76, 29, 149, 0.45) !important;
    transform: translateY(-2px) !important;
}
"""


@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def custom_swagger_ui_html():
    """Custom Swagger UI with BaluHost styling."""
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>BaluHost API Documentation</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
        <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏠</text></svg>">
        <style>
            {CUSTOM_CSS}
        </style>
    </head>
    <body>
        <div style="max-width:900px;margin:20px auto;padding:10px 20px;color:#cbd5e1;">
            <h2 style="color:#e2e8f0;margin-bottom:8px;">Operational Notes</h2>
            <p style="color:#94a3b8;margin-top:0;">This API exposes administrative operations such as a controlled <strong>/api/system/shutdown</strong> endpoint (admin-only). Calling shutdown schedules a graceful application stop and returns an ETA in seconds so clients can display a shutdown notice.</p>
            <p style="color:#94a3b8;margin-top:6px;">Energy-monitoring endpoints provide per-device power metrics (e.g. for Tapo smart plugs). Use the <code>/api/energy/*</code> endpoints to retrieve dashboard, hourly samples and cost estimates. Live power is collected by the power monitor service.</p>
        </div>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script>
            window.onload = function() {{
                window.ui = SwaggerUIBundle({{
                    url: '/openapi.json',
                    dom_id: '#swagger-ui',
                    deepLinking: true,
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIBundle.SwaggerUIStandalonePreset
                    ],
                    layout: "BaseLayout"
                }});
            }};
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/redoc", response_class=HTMLResponse, include_in_schema=False)
async def custom_redoc_html():
    """Custom ReDoc with BaluHost styling."""
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>BaluHost API Documentation - ReDoc</title>
        <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏠</text></svg>">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 25%, #1e293b 50%, #0c0a1f 75%, #020617 100%) !important;
                background-attachment: fixed !important;
            }}
            
            .menu-content {{
                background: rgba(15, 23, 42, 0.85) !important;
                backdrop-filter: blur(12px) !important;
            }}
            
            .api-content {{
                background: transparent !important;
            }}
            
            h1, h2, h3, h4, h5, h6 {{
                color: #e2e8f0 !important;
            }}
            
            p, span, div {{
                color: #94a3b8 !important;
            }}
            
            code {{
                background: rgba(0, 0, 0, 0.4) !important;
                color: #60a5fa !important;
            }}
            
            pre {{
                background: rgba(0, 0, 0, 0.6) !important;
                border: 1px solid rgba(148, 163, 184, 0.2) !important;
                border-radius: 8px !important;
            }}
        </style>
    </head>
    <body>
        <redoc spec-url="/openapi.json"></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
