import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../api/axios';

export const fetchAlerts = createAsyncThunk('alerts/list', async (params = {}) => {
  const res = await api.get('/api/alerts/list', { params });
  return res.data;
});

export const fetchAlertDetail = createAsyncThunk('alerts/detail', async (id) => {
  const res = await api.get(`/api/alerts/${id}`);
  return res.data;
});

export const updateAlertStatus = createAsyncThunk(
  'alerts/updateStatus',
  async ({ id, status }, { rejectWithValue }) => {
    try {
      await api.patch(`/api/alerts/${id}/status`, { status });
      return { id, status };
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to update status');
    }
  },
);

const slice = createSlice({
  name: 'alerts',
  initialState: { list: [], loading: false, detail: null, detailLoading: false, error: null },
  reducers: {
    clearDetail(state) { state.detail = null; },
    clearError(state) { state.error = null; },
  },
  extraReducers: (b) => {
    b.addCase(fetchAlerts.pending, (s) => { s.loading = true; })
     .addCase(fetchAlerts.fulfilled, (s, a) => { s.loading = false; s.list = a.payload; })
     .addCase(fetchAlerts.rejected, (s) => { s.loading = false; })
     .addCase(fetchAlertDetail.pending, (s) => { s.detailLoading = true; s.detail = null; })
     .addCase(fetchAlertDetail.fulfilled, (s, a) => { s.detailLoading = false; s.detail = a.payload; })
     .addCase(fetchAlertDetail.rejected, (s) => { s.detailLoading = false; })
     .addCase(updateAlertStatus.fulfilled, (s, a) => {
        const idx = s.list.findIndex((x) => x.id === a.payload.id);
        if (idx >= 0) s.list[idx].status = a.payload.status;
        if (s.detail && s.detail.id === a.payload.id) s.detail.status = a.payload.status;
     })
     .addCase(updateAlertStatus.rejected, (s, a) => { s.error = a.payload; });
  },
});

export const { clearDetail, clearError } = slice.actions;
export default slice.reducer;
