import React, { useEffect, useState } from 'react';
import {
  AppBar, Toolbar, Typography, IconButton, Badge, Box,
  Menu, MenuItem, Avatar, Tooltip, Divider,
} from '@mui/material';
import NotificationsIcon from '@mui/icons-material/Notifications';
import LogoutIcon from '@mui/icons-material/Logout';
import { useNavigate, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import ThemeToggle from './ThemeToggle';
import { logout } from '../redux/slices/authSlice';
import { fetchUnreadCount } from '../redux/slices/notificationSlice';
import { drawerWidth } from './Sidebar';

const TITLE_MAP = {
  '/': 'Dashboard',
  '/connectors': 'Connectors',
  '/datasets': 'Datasets',
  '/monitoring': 'Monitoring',
  '/alerts': 'Alerts',
  '/notifications': 'Notifications',
  '/settings': 'Settings',
};

const Header = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const user = useSelector((s) => s.auth.user);
  const unread = useSelector((s) => s.notifications.unread);
  const [anchorEl, setAnchorEl] = useState(null);

  useEffect(() => {
    dispatch(fetchUnreadCount());
    // Refresh unread count every 60 seconds (not aggressive polling)
    const t = setInterval(() => {
      dispatch(fetchUnreadCount());
    }, 60000);
    return () => clearInterval(t);
  }, [dispatch]);

  const title = TITLE_MAP[location.pathname] || 'DQ Sentinel';

  const handleLogout = () => {
    setAnchorEl(null);
    dispatch(logout());
    navigate('/login');
  };

  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={{
        width: `calc(100% - ${drawerWidth}px)`,
        ml: `${drawerWidth}px`,
        bgcolor: 'background.paper',
        color: 'text.primary',
        borderBottom: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Toolbar>
        <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 600 }}>
          {title}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <ThemeToggle />
          <Tooltip title="Notifications">
            <IconButton color="inherit" onClick={() => navigate('/notifications')}>
              <Badge badgeContent={unread} color="error" max={99}>
                <NotificationsIcon />
              </Badge>
            </IconButton>
          </Tooltip>
          <Tooltip title={user ? `${user.username} (${user.role})` : 'User'}>
            <IconButton onClick={(e) => setAnchorEl(e.currentTarget)}>
              <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: 14 }}>
                {(user?.username || 'U').slice(0, 1).toUpperCase()}
              </Avatar>
            </IconButton>
          </Tooltip>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            <MenuItem disabled>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {user?.username || '-'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {user?.email || ''} · {user?.role || ''}
                </Typography>
              </Box>
            </MenuItem>
            <Divider />
            <MenuItem onClick={() => { setAnchorEl(null); navigate('/settings'); }}>Settings</MenuItem>
            <MenuItem onClick={handleLogout}>
              <LogoutIcon fontSize="small" sx={{ mr: 1 }} /> Logout
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
