import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useSelector } from 'react-redux';

const ProtectedRoute = ({ children, roles }) => {
  const { token, user } = useSelector((s) => s.auth);
  const location = useLocation();

  if (!token) {
    return <Navigate to="/?login=1" state={{ from: location }} replace />;
  }

  if (roles && roles.length > 0 && user && !roles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
};

export default ProtectedRoute;
