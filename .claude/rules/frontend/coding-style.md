---
paths:
  - "client/**"
---
# Frontend Coding Style (React + TypeScript)

## Standards
- **Functional components** with hooks (no class components)
- **TypeScript strict mode** enabled
- **Tailwind CSS** for all styling (no inline styles)
- **API calls** through typed client in `src/lib/api.ts`
- **Error handling**: Use toast notifications (react-hot-toast)
- **Loading states**: Show loading indicators for async operations

## Example Component
```typescript
interface FileItemProps {
  file: FileItem;
  onDelete: (path: string) => Promise<void>;
}

export const FileItem: React.FC<FileItemProps> = ({ file, onDelete }) => {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(file.path);
      toast.success('File deleted');
    } catch (error) {
      toast.error('Failed to delete file');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    // JSX with Tailwind classes
  );
};
```

## Testing Strategy
- Unit tests with Vitest (configured)
- E2E tests with Playwright (configured)
- Visual regression tests (planned)
