import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import api from '../../api/axios'

export const fetchDatasets = createAsyncThunk(
  'datasets/list',
  async (params = {}, { rejectWithValue }) => {
    try {
      const res = await api.get('/api/datasets/list', { params })
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to load datasets')
    }
  },
)

export const fetchDatasetProfile = createAsyncThunk(
  'datasets/profile',
  async (id) => {
    const res = await api.get(`/api/datasets/profile/${id}`)
    return res.data
  },
)

export const runQualityCheck = createAsyncThunk(
  'datasets/quality',
  async (id, { rejectWithValue }) => {
    try {
      const res = await api.post(`/api/monitoring/quality-check/${id}`)
      return { id, ...res.data }
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Quality check failed')
    }
  },
)

export const runPiiScan = createAsyncThunk(
  'datasets/pii',
  async (id, { rejectWithValue }) => {
    try {
      const res = await api.post(`/api/monitoring/pii-scan/${id}`)
      return { id, ...res.data }
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'PII scan failed')
    }
  },
)

const slice = createSlice({
  name: 'datasets',
  initialState: { list: [], profile: null, loading: false, error: null, lastAction: null },
  reducers: {
    clearProfile(state) { state.profile = null },
    clearLastAction(state) { state.lastAction = null },
  },
  extraReducers: (b) => {
    b.addCase(fetchDatasets.pending, (s) => { s.loading = true })
     .addCase(fetchDatasets.fulfilled, (s, a) => { s.loading = false; s.list = a.payload })
     .addCase(fetchDatasets.rejected, (s) => { s.loading = false })
     .addCase(fetchDatasetProfile.fulfilled, (s, a) => { s.profile = a.payload })
     .addCase(runQualityCheck.fulfilled, (s, a) => { s.lastAction = { type: 'quality', ...a.payload } })
     .addCase(runPiiScan.fulfilled, (s, a) => { s.lastAction = { type: 'pii', ...a.payload } })
  },
})

export const { clearProfile, clearLastAction } = slice.actions
export default slice.reducer
