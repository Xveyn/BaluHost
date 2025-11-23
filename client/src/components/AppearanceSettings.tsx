import { Palette } from 'lucide-react';
import { useTheme, themes, type ThemeType } from '../contexts/ThemeContext';

export default function AppearanceSettings() {
  const { theme, setTheme } = useTheme();
  
  // Helper to convert RGB string to hex color for preview
  const rgbToColor = (rgb: string) => `rgb(${rgb})`;
  
  return (
    <div className="rounded-lg shadow bg-theme-card p-6">
      <h3 className="text-lg font-semibold mb-4 flex items-center">
        <Palette className="w-5 h-5 mr-2 text-theme-accent" />
        Color Theme
      </h3>
      <p className="mb-6 text-theme-text-secondary">
        Choose your preferred color scheme for the interface.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {(Object.keys(themes) as ThemeType[]).map(themeKey => {
          const themeColors = themes[themeKey].colors;
          return (
            <button
              key={themeKey}
              onClick={() => setTheme(themeKey)}
              className={`p-4 rounded-lg border-2 transition-all text-left ${
                theme === themeKey
                  ? 'border-theme-accent bg-theme-bg-tertiary'
                  : 'border-theme-border bg-theme-bg-secondary hover:border-theme-accent/50'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="font-semibold">{themes[themeKey].name}</span>
                {theme === themeKey && (
                  <span className="text-xs px-2 py-1 rounded bg-theme-accent text-white">
                    Active
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <div
                  className="w-8 h-8 rounded shadow-sm"
                  style={{ backgroundColor: rgbToColor(themeColors['--color-bg-primary']) }}
                  title="Background"
                />
                <div
                  className="w-8 h-8 rounded shadow-sm"
                  style={{ backgroundColor: rgbToColor(themeColors['--color-accent-primary']) }}
                  title="Accent"
                />
                <div
                  className="w-8 h-8 rounded shadow-sm"
                  style={{ backgroundColor: rgbToColor(themeColors['--color-accent-secondary']) }}
                  title="Accent Secondary"
                />
                <div
                  className="w-8 h-8 rounded shadow-sm"
                  style={{ backgroundColor: rgbToColor(themeColors['--color-sidebar-bg']) }}
                  title="Sidebar"
                />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
