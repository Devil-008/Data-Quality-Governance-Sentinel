import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../api/axios';

export const fetchSettings = createAsyncThunk('settings/list', async () => {
  const res = await api.get('/api/settings/list');
  return res.data;
});

export const updateSetting = createAsyncThunk(
  'settings/update',
  async ({ key, value }, { rejectWithValue }) => {
    try {
      await api.post('/api/settings/update', { key, value });
      return { key, value };
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to update setting');
    }
  },
);

export const changePassword = createAsyncThunk(
  'settings/changePwd',
  async ({ old_password, new_password }, { rejectWithValue }) => {
    try {
      await api.post('/api/settings/change-password', { old_password, new_password });
      return true;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to change password');
    }
  },
);

const slice = createSlice({
  name: 'settings',
  initialState: { list: [], loading: false, error: null, message: null },
  reducers: {
    clearMessage(state) { state.message = null; state.error = null; },
  },
  extraReducers: (b) => {
    b.addCase(fetchSettings.pending, (s) => { s.loading = true; })
     .addCase(fetchSettings.fulfilled, (s, a) => { s.loading = false; s.list = a.payload; })
     .addCase(fetchSettings.rejected, (s) => { s.loading = false; })
     .addCase(updateSetting.fulfilled, (s, a) => {
        const idx = s.list.findIndex((x) => x.setting_key === a.payload.key);
        if (idx >= 0) s.list[idx].setting_value = a.payload.value;
        else s.list.push({ setting_key: a.payload.key, setting_value: a.payload.value });
        s.message = 'Setting updated';
     })
     .addCase(updateSetting.rejected, (s, a) => { s.error = a.payload; })
     .addCase(changePassword.fulfilled, (s) => { s.message = 'Password changed successfully'; })
     .addCase(changePassword.rejected, (s, a) => { s.error = a.payload; });
  },
});

export const { clearMessage } = slice.actions;
export default slice.reducer;
