import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogContent, Box, Card, CardContent, TextField, Button, Typography,
  Alert, InputAdornment, IconButton, Stack,
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import ShieldIcon from '@mui/icons-material/Shield';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { login, clearError } from '../../redux/slices/authSlice';

const Login = ({ open = true, onClose, onSuccess }) => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { loading, error, token } = useSelector((s) => s.auth);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);

  useEffect(() => {
    if (token) {
      if (onSuccess) onSuccess();
      else navigate('/dashboard', { replace: true });
    }
  }, [token, navigate, onSuccess]);

  useEffect(() => {
    return () => { dispatch(clearError()); };
  }, [dispatch]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const result = await dispatch(login({ username, password }));
    if (login.fulfilled.match(result)) {
      if (onSuccess) onSuccess();
      else navigate('/dashboard', { replace: true });
    }
  };

  return (
    <Dialog 
      open={open} 
      onClose={onClose} 
      maxWidth="xs" 
      fullWidth 
      PaperProps={{ 
        sx: { 
          borderRadius: 3, 
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)' 
        } 
      }}
      slotProps={{
        backdrop: {
          sx: {
            background: 'linear-gradient(135deg, #2563eb 0%, #1e40af 50%, #0f172a 100%)',
          }
        }
      }}
    >
      <CardContent sx={{ p: 4 }}>
        <Stack alignItems="center" spacing={1} sx={{ mb: 3 }}>
          <Box
            sx={{
              width: 64, height: 64, borderRadius: 2,
              bgcolor: 'primary.main', display: 'flex',
              alignItems: 'center', justifyContent: 'center',
            }}
          >
            <ShieldIcon sx={{ color: '#fff', fontSize: 36 }} />
          </Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>DQ Sentinel</Typography>
          <Typography variant="body2" color="text.secondary" align="center">
            AI-Powered Data Quality, Governance &amp; Observability
          </Typography>
        </Stack>

        <form onSubmit={handleSubmit}>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              fullWidth
              autoFocus
            />
            <TextField
              label="Password"
              type={showPwd ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              fullWidth
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPwd((s) => !s)} edge="end" size="small">
                      {showPwd ? <VisibilityOffIcon /> : <VisibilityIcon />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <Button
              type="submit"
              variant="contained"
              size="large"
              disabled={loading || !username || !password}
              fullWidth
              sx={{ py: 1.5, fontWeight: 600 }}
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </Button>
            <Typography variant="caption" align="center" color="text.secondary">
              Default credentials: <strong>admin / Admin@123</strong>
            </Typography>
          </Stack>
        </form>
      </CardContent>
    </Dialog>
  );
};

export default Login;
