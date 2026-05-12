import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../api/axios';

export const fetchConnectors = createAsyncThunk('connectors/list', async () => {
  const res = await api.get('/api/connectors/list');
  return res.data;
});

export const createConnector = createAsyncThunk(
  'connectors/create',
  async (payload, { rejectWithValue }) => {
    try {
      const res = await api.post('/api/connectors/create', payload);
      return res.data;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to create connector');
    }
  },
);

export const testConnection = createAsyncThunk(
  'connectors/test',
  async (payload, { rejectWithValue }) => {
    try {
      const res = await api.post('/api/connectors/test-connection', payload);
      return res.data;
    } catch (e) {
      return rejectWithValue(
        e.response?.data?.detail
          ? { success: false, message: e.response.data.detail }
          : { success: false, message: 'Connection test failed' },
      );
    }
  },
);

export const testExistingConnector = createAsyncThunk(
  'connectors/testExisting',
  async (id, { rejectWithValue }) => {
    try {
      const res = await api.post(`/api/connectors/${id}/test`);
      return res.data;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Test failed');
    }
  },
);

export const scanConnector = createAsyncThunk(
  'connectors/scan',
  async (id, { rejectWithValue }) => {
    try {
      const res = await api.post(`/api/monitoring/scan/${id}`);
      return res.data;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Scan failed');
    }
  },
);

export const deleteConnector = createAsyncThunk(
  'connectors/delete',
  async (id, { rejectWithValue }) => {
    try {
      await api.delete(`/api/connectors/${id}`);
      return id;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Delete failed');
    }
  },
);

const slice = createSlice({
  name: 'connectors',
  initialState: {
    list: [],
    loading: false,
    error: null,
    testResult: null,
    scanResult: null,
    testLoading: false,
    scanLoading: false,
  },
  reducers: {
    clearTestResult(state) { state.testResult = null; },
    clearScanResult(state) { state.scanResult = null; },
    clearError(state) { state.error = null; },
  },
  extraReducers: (b) => {
    b.addCase(fetchConnectors.pending, (s) => { s.loading = true; s.error = null; })
     .addCase(fetchConnectors.fulfilled, (s, a) => { s.loading = false; s.list = a.payload; })
     .addCase(fetchConnectors.rejected, (s, a) => { s.loading = false; s.error = a.error?.message; })
     .addCase(createConnector.pending, (s) => { s.loading = true; })
     .addCase(createConnector.fulfilled, (s, a) => { s.loading = false; s.list = [a.payload, ...s.list]; })
     .addCase(createConnector.rejected, (s, a) => { s.loading = false; s.error = a.payload; })
     .addCase(deleteConnector.fulfilled, (s, a) => { s.list = s.list.filter((c) => c.id !== a.payload); })
     .addCase(testConnection.pending, (s) => { s.testLoading = true; s.testResult = null; })
     .addCase(testConnection.fulfilled, (s, a) => { s.testLoading = false; s.testResult = a.payload; })
     .addCase(testConnection.rejected, (s, a) => { s.testLoading = false; s.testResult = a.payload || { success: false, message: 'Failed' }; })
     .addCase(testExistingConnector.pending, (s) => { s.testLoading = true; })
     .addCase(testExistingConnector.fulfilled, (s, a) => { s.testLoading = false; s.testResult = a.payload; })
     .addCase(testExistingConnector.rejected, (s, a) => { s.testLoading = false; s.testResult = { success: false, message: a.payload }; })
     .addCase(scanConnector.pending, (s) => { s.scanLoading = true; s.scanResult = null; })
     .addCase(scanConnector.fulfilled, (s, a) => { s.scanLoading = false; s.scanResult = a.payload; })
     .addCase(scanConnector.rejected, (s, a) => { s.scanLoading = false; s.scanResult = { status: 'failed', error: a.payload }; });
  },
});

export const { clearTestResult, clearScanResult, clearError } = slice.actions;
export default slice.reducer;
