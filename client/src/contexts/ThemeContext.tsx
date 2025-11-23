import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

export type ThemeType = 'light' | 'dark' | 'ocean' | 'forest' | 'sunset' | 'midnight';

interface ThemeContextType {
  theme: ThemeType;
  setTheme: (theme: ThemeType) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const themes = {
  light: {
    name: 'Light',
    colors: {
      '--color-bg-primary': '255, 255, 255',        // #ffffff
      '--color-bg-secondary': '248, 250, 252',      // #f8fafc
      '--color-bg-tertiary': '241, 245, 249',       // #f1f5f9
      '--color-text-primary': '15, 23, 42',         // #0f172a
      '--color-text-secondary': '71, 85, 105',      // #475569
      '--color-text-tertiary': '100, 116, 139',     // #64748b
      '--color-border-primary': '226, 232, 240',    // #e2e8f0
      '--color-border-secondary': '203, 213, 225',  // #cbd5e1
      '--color-accent-primary': '59, 130, 246',     // #3b82f6
      '--color-accent-secondary': '37, 99, 235',    // #2563eb
      '--color-accent-hover': '29, 78, 216',        // #1d4ed8
      '--color-sidebar-bg': '255, 255, 255',        // #ffffff
      '--color-sidebar-text': '71, 85, 105',        // #475569
      '--color-sidebar-hover': '241, 245, 249',     // #f1f5f9
      '--color-sidebar-active': '59, 130, 246',     // #3b82f6
      '--color-card-bg': '255, 255, 255',           // #ffffff
    }
  },
  dark: {
    name: 'Dark',
    colors: {
      '--color-bg-primary': '15, 23, 42',           // slate-950 #0f172a
      '--color-bg-secondary': '30, 41, 59',         // slate-900 #1e293b
      '--color-bg-tertiary': '51, 65, 85',          // slate-800 #334155
      '--color-text-primary': '241, 245, 249',      // slate-100 #f1f5f9
      '--color-text-secondary': '203, 213, 225',    // slate-300 #cbd5e1
      '--color-text-tertiary': '148, 163, 184',     // slate-400 #94a3b8
      '--color-border-primary': '51, 65, 85',       // slate-800 #334155
      '--color-border-secondary': '71, 85, 105',    // slate-700 #475569
      '--color-accent-primary': '56, 189, 248',     // sky-400 #38bdf8
      '--color-accent-secondary': '96, 165, 250',   // blue-400 #60a5fa
      '--color-accent-hover': '147, 197, 253',      // blue-300 #93c5fd
      '--color-sidebar-bg': '30, 41, 59',           // slate-900 #1e293b
      '--color-sidebar-text': '203, 213, 225',      // slate-300 #cbd5e1
      '--color-sidebar-hover': '51, 65, 85',        // slate-800 #334155
      '--color-sidebar-active': '56, 189, 248',     // sky-400 #38bdf8
      '--color-card-bg': '30, 41, 59',              // slate-900 #1e293b
    }
  },
  ocean: {
    name: 'Ocean',
    colors: {
      '--color-bg-primary': '12, 30, 46',           // #0c1e2e
      '--color-bg-secondary': '15, 41, 66',         // #0f2942
      '--color-bg-tertiary': '26, 58, 82',          // #1a3a52
      '--color-text-primary': '224, 242, 254',      // #e0f2fe
      '--color-text-secondary': '125, 211, 252',    // #7dd3fc
      '--color-text-tertiary': '56, 189, 248',      // #38bdf8
      '--color-border-primary': '12, 74, 110',      // #0c4a6e
      '--color-border-secondary': '7, 89, 133',     // #075985
      '--color-accent-primary': '6, 182, 212',      // #06b6d4
      '--color-accent-secondary': '8, 145, 178',    // #0891b2
      '--color-accent-hover': '14, 116, 144',       // #0e7490
      '--color-sidebar-bg': '15, 41, 66',           // #0f2942
      '--color-sidebar-text': '125, 211, 252',      // #7dd3fc
      '--color-sidebar-hover': '26, 58, 82',        // #1a3a52
      '--color-sidebar-active': '6, 182, 212',      // #06b6d4
      '--color-card-bg': '15, 41, 66',              // #0f2942
    }
  },
  forest: {
    name: 'Forest',
    colors: {
      '--color-bg-primary': '20, 18, 11',           // #14120b
      '--color-bg-secondary': '28, 38, 23',         // #1c2617
      '--color-bg-tertiary': '45, 59, 39',          // #2d3b27
      '--color-text-primary': '240, 253, 244',      // #f0fdf4
      '--color-text-secondary': '187, 247, 208',    // #bbf7d0
      '--color-text-tertiary': '134, 239, 172',     // #86efac
      '--color-border-primary': '54, 83, 20',       // #365314
      '--color-border-secondary': '77, 124, 15',    // #4d7c0f
      '--color-accent-primary': '34, 197, 94',      // #22c55e
      '--color-accent-secondary': '22, 163, 74',    // #16a34a
      '--color-accent-hover': '21, 128, 61',        // #15803d
      '--color-sidebar-bg': '28, 38, 23',           // #1c2617
      '--color-sidebar-text': '187, 247, 208',      // #bbf7d0
      '--color-sidebar-hover': '45, 59, 39',        // #2d3b27
      '--color-sidebar-active': '34, 197, 94',      // #22c55e
      '--color-card-bg': '28, 38, 23',              // #1c2617
    }
  },
  sunset: {
    name: 'Sunset',
    colors: {
      '--color-bg-primary': '45, 27, 30',           // #2d1b1e
      '--color-bg-secondary': '63, 40, 50',         // #3f2832
      '--color-bg-tertiary': '82, 51, 63',          // #52333f
      '--color-text-primary': '254, 242, 242',      // #fef2f2
      '--color-text-secondary': '254, 205, 211',    // #fecdd3
      '--color-text-tertiary': '253, 164, 175',     // #fda4af
      '--color-border-primary': '136, 19, 55',      // #881337
      '--color-border-secondary': '159, 18, 57',    // #9f1239
      '--color-accent-primary': '244, 63, 94',      // #f43f5e
      '--color-accent-secondary': '225, 29, 72',    // #e11d48
      '--color-accent-hover': '190, 18, 60',        // #be123c
      '--color-sidebar-bg': '63, 40, 50',           // #3f2832
      '--color-sidebar-text': '254, 205, 211',      // #fecdd3
      '--color-sidebar-hover': '82, 51, 63',        // #52333f
      '--color-sidebar-active': '244, 63, 94',      // #f43f5e
      '--color-card-bg': '63, 40, 50',              // #3f2832
    }
  },
  midnight: {
    name: 'Midnight',
    colors: {
      '--color-bg-primary': '10, 10, 15',           // #0a0a0f
      '--color-bg-secondary': '22, 22, 31',         // #16161f
      '--color-bg-tertiary': '31, 31, 46',          // #1f1f2e
      '--color-text-primary': '233, 213, 255',      // #e9d5ff
      '--color-text-secondary': '196, 181, 253',    // #c4b5fd
      '--color-text-tertiary': '167, 139, 250',     // #a78bfa
      '--color-border-primary': '76, 29, 149',      // #4c1d95
      '--color-border-secondary': '91, 33, 182',    // #5b21b6
      '--color-accent-primary': '139, 92, 246',     // #8b5cf6
      '--color-accent-secondary': '124, 58, 237',   // #7c3aed
      '--color-accent-hover': '109, 40, 217',       // #6d28d9
      '--color-sidebar-bg': '22, 22, 31',           // #16161f
      '--color-sidebar-text': '196, 181, 253',      // #c4b5fd
      '--color-sidebar-hover': '31, 31, 46',        // #1f1f2e
      '--color-sidebar-active': '139, 92, 246',     // #8b5cf6
      '--color-card-bg': '22, 22, 31',              // #16161f
    }
  }
};

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeType>(() => {
    const saved = localStorage.getItem('theme');
    return (saved as ThemeType) || 'dark';
  });

  useEffect(() => {
    // Apply theme colors to CSS variables
    const themeColors = themes[theme].colors;
    const root = document.documentElement;
    
    Object.entries(themeColors).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });

    // Save to localStorage
    localStorage.setItem('theme', theme);
  }, [theme]);

  const setTheme = (newTheme: ThemeType) => {
    setThemeState(newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    // Fallback for when ThemeProvider is not available
    console.warn('useTheme: ThemeProvider not found, using default theme');
    return {
      theme: 'dark' as ThemeType,
      setTheme: () => console.warn('ThemeProvider not available')
    };
  }
  return context;
}
