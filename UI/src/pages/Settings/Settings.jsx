import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Card, CardContent, Stack, TextField, Button, Alert,
  Divider, Grid, Chip,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import LockResetIcon from '@mui/icons-material/LockReset';
import EmailIcon from '@mui/icons-material/Email';
import PaletteIcon from '@mui/icons-material/Palette';
import { useDispatch, useSelector } from 'react-redux';
import {
  fetchSettings, updateSetting, changePassword, clearMessage,
} from '../../redux/slices/settingsSlice';
import { toggleTheme } from '../../redux/slices/themeSlice';

const SettingsPage = () => {
  const dispatch = useDispatch();
  const { list, message, error } = useSelector((s) => s.settings);
  const user = useSelector((s) => s.auth.user);
  const themeMode = useSelector((s) => s.theme.mode);

  const [recipients, setRecipients] = useState('');
  const [recipientsQuality, setRecipientsQuality] = useState('');
  const [recipientsSchemaDrift, setRecipientsSchemaDrift] = useState('');
  const [recipientsPii, setRecipientsPii] = useState('');
  const [recipientsGovernance, setRecipientsGovernance] = useState('');
  const [recipientsPipeline, setRecipientsPipeline] = useState('');
  const [recipientsCloud, setRecipientsCloud] = useState('');
  const [recipientsDatabricks, setRecipientsDatabricks] = useState('');
  const [defaultInterval, setDefaultInterval] = useState('60');
  const [aiEnabled, setAiEnabled] = useState('1');
  const [pwd, setPwd] = useState({ old_password: '', new_password: '', confirm: '' });
  const [pwdError, setPwdError] = useState(null);

  useEffect(() => {
    dispatch(fetchSettings());
    return () => { dispatch(clearMessage()); };
  }, [dispatch]);

  useEffect(() => {
    if (!list) return;
    const find = (k) => (list.find((s) => s.setting_key === k) || {}).setting_value || '';
    setRecipients(find('alert_email_recipients'));
    setRecipientsQuality(find('email_recipients_quality'));
    setRecipientsSchemaDrift(find('email_recipients_schema_drift'));
    setRecipientsPii(find('email_recipients_pii'));
    setRecipientsGovernance(find('email_recipients_governance'));
    setRecipientsPipeline(find('email_recipients_pipeline'));
    setRecipientsCloud(find('email_recipients_cloud'));
    setRecipientsDatabricks(find('email_recipients_databricks'));
    setDefaultInterval(find('default_scan_interval_minutes') || '60');
    setAiEnabled(find('ai_enabled') || '1');
  }, [list]);

  const save = async (key, value) => {
    await dispatch(updateSetting({ key, value }));
  };

  const handlePwdChange = async () => {
    setPwdError(null);
    if (!pwd.old_password || !pwd.new_password) {
      setPwdError('Both fields are required');
      return;
    }
    if (pwd.new_password !== pwd.confirm) {
      setPwdError('Passwords do not match');
      return;
    }
    if (pwd.new_password.length < 6) {
      setPwdError('Password must be at least 6 characters');
      return;
    }
    const res = await dispatch(changePassword({
      old_password: pwd.old_password,
      new_password: pwd.new_password,
    }));
    if (changePassword.fulfilled.match(res)) {
      setPwd({ old_password: '', new_password: '', confirm: '' });
    }
  };

  const isAdmin = user?.role === 'admin';

  return (
    <Box>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>Settings</Typography>

      {message && <Alert severity="success" sx={{ mb: 2 }} onClose={() => dispatch(clearMessage())}>{message}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => dispatch(clearMessage())}>{error}</Alert>}

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                <EmailIcon color="primary" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Alert Email Recipients</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
                Comma-separated email addresses that will receive alert emails. Leave blank to disable.
              </Typography>
              <TextField
                fullWidth
                size="small"
                placeholder="ops@example.com, data-team@example.com"
                value={recipients}
                onChange={(e) => setRecipients(e.target.value)}
                disabled={!isAdmin}
                sx={{ mb: 2 }}
              />
              <Button
                variant="contained" size="small"
                startIcon={<SaveIcon />}
                onClick={() => save('alert_email_recipients', recipients)}
                disabled={!isAdmin}
              >
                Save Recipients
              </Button>
              {!isAdmin && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                  Only admins can update this setting.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                <EmailIcon color="primary" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Category Routing</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: 'block' }}>
                Specify different emails per category. Fallbacks to default if left blank.
              </Typography>
              <Stack spacing={2} sx={{ maxHeight: 300, overflowY: 'auto', pr: 1 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Data Quality Alerts</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                    <TextField fullWidth size="small" value={recipientsQuality} onChange={(e) => setRecipientsQuality(e.target.value)} placeholder="Quality team emails" disabled={!isAdmin} />
                    <Button variant="outlined" size="small" onClick={() => save('email_recipients_quality', recipientsQuality)} disabled={!isAdmin}>Save</Button>
                  </Stack>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Schema Drift Alerts</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                    <TextField fullWidth size="small" value={recipientsSchemaDrift} onChange={(e) => setRecipientsSchemaDrift(e.target.value)} placeholder="Schema team emails" disabled={!isAdmin} />
                    <Button variant="outlined" size="small" onClick={() => save('email_recipients_schema_drift', recipientsSchemaDrift)} disabled={!isAdmin}>Save</Button>
                  </Stack>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>PII Exposure Alerts</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                    <TextField fullWidth size="small" value={recipientsPii} onChange={(e) => setRecipientsPii(e.target.value)} placeholder="Privacy team emails" disabled={!isAdmin} />
                    <Button variant="outlined" size="small" onClick={() => save('email_recipients_pii', recipientsPii)} disabled={!isAdmin}>Save</Button>
                  </Stack>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Governance Violations</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                    <TextField fullWidth size="small" value={recipientsGovernance} onChange={(e) => setRecipientsGovernance(e.target.value)} placeholder="Governance team emails" disabled={!isAdmin} />
                    <Button variant="outlined" size="small" onClick={() => save('email_recipients_governance', recipientsGovernance)} disabled={!isAdmin}>Save</Button>
                  </Stack>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Pipeline Failures</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                    <TextField fullWidth size="small" value={recipientsPipeline} onChange={(e) => setRecipientsPipeline(e.target.value)} placeholder="Ops team emails" disabled={!isAdmin} />
                    <Button variant="outlined" size="small" onClick={() => save('email_recipients_pipeline', recipientsPipeline)} disabled={!isAdmin}>Save</Button>
                  </Stack>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Cloud Systems</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                    <TextField fullWidth size="small" value={recipientsCloud} onChange={(e) => setRecipientsCloud(e.target.value)} placeholder="Cloud team emails" disabled={!isAdmin} />
                    <Button variant="outlined" size="small" onClick={() => save('email_recipients_cloud', recipientsCloud)} disabled={!isAdmin}>Save</Button>
                  </Stack>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Databricks Specific</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                    <TextField fullWidth size="small" value={recipientsDatabricks} onChange={(e) => setRecipientsDatabricks(e.target.value)} placeholder="Databricks team emails" disabled={!isAdmin} />
                    <Button variant="outlined" size="small" onClick={() => save('email_recipients_databricks', recipientsDatabricks)} disabled={!isAdmin}>Save</Button>
                  </Stack>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                <PaletteIcon color="primary" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Appearance</Typography>
              </Stack>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Current theme: <Chip label={themeMode} size="small" sx={{ ml: 1 }} />
              </Typography>
              <Button variant="outlined" size="small" onClick={() => dispatch(toggleTheme())}>
                Toggle Theme
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
                Default Scan Interval
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
                Default interval (minutes) for new monitoring jobs.
              </Typography>
              <TextField
                type="number"
                size="small"
                value={defaultInterval}
                onChange={(e) => setDefaultInterval(e.target.value)}
                disabled={!isAdmin}
                sx={{ mb: 2, width: 200 }}
              />
              <br />
              <Button
                variant="contained" size="small"
                startIcon={<SaveIcon />}
                onClick={() => save('default_scan_interval_minutes', defaultInterval)}
                disabled={!isAdmin}
              >
                Save
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
                AI Analysis
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
                Enable Mistral AI analysis for new alerts. Requires MISTRAL_API_KEY in backend .env.
              </Typography>
              <TextField
                select
                size="small"
                SelectProps={{ native: true }}
                value={aiEnabled}
                onChange={(e) => setAiEnabled(e.target.value)}
                disabled={!isAdmin}
                sx={{ mb: 2, width: 200 }}
              >
                <option value="1">Enabled</option>
                <option value="0">Disabled</option>
              </TextField>
              <br />
              <Button
                variant="contained" size="small"
                startIcon={<SaveIcon />}
                onClick={() => save('ai_enabled', aiEnabled)}
                disabled={!isAdmin}
              >
                Save
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                <LockResetIcon color="primary" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Change Password</Typography>
              </Stack>
              {pwdError && <Alert severity="error" sx={{ mb: 2 }}>{pwdError}</Alert>}
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <TextField
                  label="Current Password"
                  type="password"
                  size="small"
                  value={pwd.old_password}
                  onChange={(e) => setPwd((p) => ({ ...p, old_password: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="New Password"
                  type="password"
                  size="small"
                  value={pwd.new_password}
                  onChange={(e) => setPwd((p) => ({ ...p, new_password: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Confirm New Password"
                  type="password"
                  size="small"
                  value={pwd.confirm}
                  onChange={(e) => setPwd((p) => ({ ...p, confirm: e.target.value }))}
                  sx={{ flex: 1 }}
                />
                <Button variant="contained" onClick={handlePwdChange}>Update</Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>User Profile</Typography>
              <Stack direction="row" spacing={4}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Username</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>{user?.username || '-'}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Email</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>{user?.email || '-'}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Role</Typography>
                  <Chip label={user?.role || '-'} size="small" sx={{ mt: 0.5 }} />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default SettingsPage;
