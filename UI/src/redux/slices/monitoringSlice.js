import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../api/axios';

export const fetchJobs = createAsyncThunk('monitoring/jobs', async () => {
  const res = await api.get('/api/monitoring/jobs');
  return res.data;
});

export const fetchRuns = createAsyncThunk('monitoring/runs', async (limit = 50) => {
  const res = await api.get('/api/monitoring/runs', { params: { limit } });
  return res.data;
});

export const createJob = createAsyncThunk(
  'monitoring/createJob',
  async (body, { rejectWithValue }) => {
    try {
      const res = await api.post('/api/monitoring/jobs', body);
      return res.data;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to create job');
    }
  },
);

export const deleteJob = createAsyncThunk(
  'monitoring/deleteJob',
  async (id, { rejectWithValue }) => {
    try {
      await api.delete(`/api/monitoring/jobs/${id}`);
      return id;
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to delete job');
    }
  },
);

const slice = createSlice({
  name: 'monitoring',
  initialState: { jobs: [], runs: [], loading: false, error: null },
  reducers: {
    clearError(state) { state.error = null; },
  },
  extraReducers: (b) => {
    b.addCase(fetchJobs.pending, (s) => { s.loading = true; })
     .addCase(fetchJobs.fulfilled, (s, a) => { s.loading = false; s.jobs = a.payload; })
     .addCase(fetchJobs.rejected, (s) => { s.loading = false; })
     .addCase(fetchRuns.fulfilled, (s, a) => { s.runs = a.payload; })
     .addCase(createJob.fulfilled, (s) => { /* refetch via component */ })
     .addCase(createJob.rejected, (s, a) => { s.error = a.payload; })
     .addCase(deleteJob.fulfilled, (s, a) => { s.jobs = s.jobs.filter((j) => j.id !== a.payload); });
  },
});

export const { clearError } = slice.actions;
export default slice.reducer;
