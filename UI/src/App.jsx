import React, { useMemo } from 'react';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { BrowserRouter } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { getTheme } from './theme/theme';
import AppRoutes from './routes/AppRoutes';

const App = () => {
  const mode = useSelector((s) => s.theme.mode);
  const theme = useMemo(() => getTheme(mode), [mode]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ThemeProvider>
  );
};

export default App;
