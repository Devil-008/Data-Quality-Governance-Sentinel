import { createTheme } from '@mui/material/styles'

const common = {
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif',
    h6: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
}

export const lightTheme = createTheme({
  ...common,
  palette: {
    mode: 'light',
    primary: { main: '#e0875a' },
    secondary: { main: '#7c3aed' },
    background: { default: '#f6f3ec', paper: '#fbf8f1' },
    text: { primary: '#0f172a', secondary: '#475569' },
    divider: '#e2e8f0',
    success: { main: '#16a34a' },
    warning: { main: '#d97706' },
    error: { main: '#dc2626' },
    info: { main: '#0284c7' },
  },
})

export const darkTheme = createTheme({
  ...common,
  palette: {
    mode: 'dark',
    primary: { main: '#d97742' },
    secondary: { main: '#a78bfa' },
    background: { default: '#0a0a0c', paper: '#111114' },
    text: { primary: '#e5e7eb', secondary: '#94a3b8' },
    divider: '#1f2937',
    success: { main: '#22c55e' },
    warning: { main: '#f59e0b' },
    error: { main: '#ef4444' },
    info: { main: '#38bdf8' },
  },
})

export const getTheme = (mode) => (mode === 'dark' ? darkTheme : lightTheme)
