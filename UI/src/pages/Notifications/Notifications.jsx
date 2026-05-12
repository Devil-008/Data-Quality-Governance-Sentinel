import React, { useEffect } from 'react';
import {
  Box, Typography, Card, CardContent, Stack, Button, Paper,
  List, ListItem, ListItemText, ListItemIcon, IconButton, Chip, Divider,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import CircleIcon from '@mui/icons-material/Circle';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  fetchNotifications, fetchUnreadCount, markRead, markAllRead,
} from '../../redux/slices/notificationSlice';

const Notifications = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { list, unread } = useSelector((s) => s.notifications);

  useEffect(() => {
    dispatch(fetchNotifications());
    dispatch(fetchUnreadCount());
  }, [dispatch]);

  const refresh = () => {
    dispatch(fetchNotifications());
    dispatch(fetchUnreadCount());
  };

  const handleMarkAll = async () => {
    await dispatch(markAllRead());
    refresh();
  };

  const handleClickItem = (n) => {
    if (!n.is_read) dispatch(markRead(n.id));
    if (n.alert_id) navigate(`/alerts?id=${n.alert_id}`);
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Notifications</Typography>
          {unread > 0 && <Chip label={`${unread} unread`} color="error" size="small" />}
        </Stack>
        <Stack direction="row" spacing={1}>
          <Button startIcon={<RefreshIcon />} onClick={refresh} variant="outlined">Refresh</Button>
          <Button startIcon={<DoneAllIcon />} onClick={handleMarkAll} variant="contained" disabled={unread === 0}>
            Mark All Read
          </Button>
        </Stack>
      </Stack>

      <Card>
        <CardContent sx={{ p: 0 }}>
          {!list || list.length === 0 ? (
            <Box sx={{ p: 6, textAlign: 'center' }}>
              <NotificationsActiveIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
              <Typography color="text.secondary">
                No notifications yet. Alerts will appear here when triggered.
              </Typography>
            </Box>
          ) : (
            <List sx={{ p: 0 }}>
              {list.map((n, i) => (
                <React.Fragment key={n.id}>
                  <ListItem
                    button
                    onClick={() => handleClickItem(n)}
                    sx={{
                      bgcolor: n.is_read ? 'transparent' : 'action.hover',
                      py: 1.5,
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      {n.is_read ? (
                        <CheckCircleIcon fontSize="small" color="disabled" />
                      ) : (
                        <CircleIcon fontSize="small" color="primary" sx={{ fontSize: 12 }} />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Typography variant="body2" sx={{ fontWeight: n.is_read ? 400 : 600 }}>
                          {n.title}
                        </Typography>
                      }
                      secondary={
                        <Box>
                          {n.message && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                              {n.message}
                            </Typography>
                          )}
                          <Typography variant="caption" color="text.disabled">
                            {n.created_at ? new Date(n.created_at).toLocaleString() : '-'}
                          </Typography>
                        </Box>
                      }
                    />
                    {!n.is_read && (
                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); dispatch(markRead(n.id)); }}>
                        <CheckCircleIcon fontSize="small" />
                      </IconButton>
                    )}
                  </ListItem>
                  {i < list.length - 1 && <Divider />}
                </React.Fragment>
              ))}
            </List>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

export default Notifications;
