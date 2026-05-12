import { configureStore } from '@reduxjs/toolkit';
import auth from './slices/authSlice';
import theme from './slices/themeSlice';
import dashboard from './slices/dashboardSlice';
import connectors from './slices/connectorSlice';
import datasets from './slices/datasetSlice';
import alerts from './slices/alertSlice';
import notifications from './slices/notificationSlice';
import monitoring from './slices/monitoringSlice';
import settings from './slices/settingsSlice';

export const store = configureStore({
  reducer: { auth, theme, dashboard, connectors, datasets, alerts, notifications, monitoring, settings },
  middleware: (gDM) => gDM({ serializableCheck: false }),
});

export default store;
