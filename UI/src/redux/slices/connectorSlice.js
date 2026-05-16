import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../api/axios';

export const fetchConnectors = createAsyncThunk(
  'connectors/list',
  async (_, { rejectWithValue, getState }) => {
    const { connectors } = getState()
    if (connectors.list.length > 0 && !connectors.loading) {
      return connectors.list
    }
    try {
      const res = await api.get('/api/connectors/list')
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to load connectors')
    }
  },
)

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

export const qualityCheckAllDatasets = createAsyncThunk(
  'connectors/qualityCheckAll',
  async (id, { rejectWithValue }) => {
    try {
      const res = await api.post(`/api/monitoring/quality-check-all/${id}`);
      return res.data;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Quality check failed');
    }
  },
);

export const updateConnector = createAsyncThunk(
  'connectors/update',
  async (payload, { rejectWithValue }) => {
    try {
      const res = await api.put(`/api/connectors/${payload.id}`, { 
        name: payload.name, 
        type: payload.type, 
        config: payload.config,
        dataset_credentials: payload.dataset_credentials
      });
      return res.data;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to update connector');
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
    qualityCheckAllResult: null,
    testLoading: false,
    scanLoading: false,
    qualityCheckAllLoading: false,
  },
  reducers: {
    clearTestResult(state) { state.testResult = null; },
    clearScanResult(state) { state.scanResult = null; },
    clearQualityCheckAllResult(state) { state.qualityCheckAllResult = null; },
    clearError(state) { state.error = null; },
  },
  extraReducers: (b) => {
    b.addCase(fetchConnectors.pending, (s) => { s.loading = true; s.error = null; })
     .addCase(fetchConnectors.fulfilled, (s, a) => { s.loading = false; s.list = a.payload; })
     .addCase(fetchConnectors.rejected, (s, a) => { s.loading = false; s.error = a.error?.message; })
     .addCase(createConnector.pending, (s) => { s.loading = true; })
     .addCase(createConnector.fulfilled, (s, a) => { s.loading = false; s.list = [a.payload, ...s.list]; })
     .addCase(createConnector.rejected, (s, a) => { s.loading = false; s.error = a.payload; })
     .addCase(updateConnector.fulfilled, (s, a) => { 
       s.loading = false; 
       s.list = s.list.map((c) => c.id === a.payload.id ? a.payload : c); 
     })
     .addCase(updateConnector.rejected, (s, a) => { s.loading = false; s.error = a.payload; })
     .addCase(deleteConnector.fulfilled, (s, a) => { s.list = s.list.filter((c) => c.id !== a.payload); })
     .addCase(testConnection.pending, (s) => { s.testLoading = true; s.testResult = null; })
     .addCase(testConnection.fulfilled, (s, a) => { s.testLoading = false; s.testResult = a.payload; })
     .addCase(testConnection.rejected, (s, a) => { s.testLoading = false; s.testResult = a.payload || { success: false, message: 'Failed' }; })
     .addCase(testExistingConnector.pending, (s) => { s.testLoading = true; })
     .addCase(testExistingConnector.fulfilled, (s, a) => { s.testLoading = false; s.testResult = a.payload; })
     .addCase(testExistingConnector.rejected, (s, a) => { s.testLoading = false; s.testResult = { success: false, message: a.payload }; })
     .addCase(scanConnector.pending, (s) => { s.scanLoading = true; s.scanResult = null; })
     .addCase(scanConnector.fulfilled, (s, a) => { s.scanLoading = false; s.scanResult = a.payload; })
     .addCase(scanConnector.rejected, (s, a) => { s.scanLoading = false; s.scanResult = { status: 'failed', error: a.payload }; })
     .addCase(qualityCheckAllDatasets.pending, (s) => { s.qualityCheckAllLoading = true; s.qualityCheckAllResult = null; })
     .addCase(qualityCheckAllDatasets.fulfilled, (s, a) => { s.qualityCheckAllLoading = false; s.qualityCheckAllResult = a.payload; })
     .addCase(qualityCheckAllDatasets.rejected, (s, a) => { s.qualityCheckAllLoading = false; s.qualityCheckAllResult = { status: 'failed', error: a.payload }; });
  },
});

export const { clearTestResult, clearScanResult, clearQualityCheckAllResult, clearError } = slice.actions;
export default slice.reducer;
