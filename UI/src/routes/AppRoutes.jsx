import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import ProtectedRoute from '../components/ProtectedRoute';
import Layout from '../components/Layout';
import Landing from '../pages/Landing/Landing';
import Login from '../pages/Login/Login';
// import Login2 from '../pages/Login/Login2';
import Dashboard from '../pages/Dashboard/Dashboard';
import Connectors from '../pages/Connectors/Connectors';
import Datasets from '../pages/Datasets/Datasets';
import Monitoring from '../pages/Monitoring/Monitoring';
import Alerts from '../pages/Alerts/Alerts';
import Notifications from '../pages/Notifications/Notifications';
import Settings from '../pages/Settings/Settings';

const AppRoutes = () => {
  return (
    <Routes>
 <Route path="/" element={<Landing />} />
      {/* <Route path="/login" element={<Login2 />} /> */}
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/connectors" element={<Connectors />} />
        <Route path="/datasets" element={<Datasets />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default AppRoutes;
