import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import api from '../../api/axios'

export const fetchDashboardStats = createAsyncThunk(
  'dashboard/fetchStats',
  async (_, { rejectWithValue }) => {
    try {
      const res = await api.get('/api/dashboard/stats')
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to load dashboard stats')
    }
  },
)

export const fetchRecentActivity = createAsyncThunk(
  'dashboard/fetchRecentActivity',
  async (_, { rejectWithValue }) => {
    try {
      const res = await api.get('/api/dashboard/recent-activity')
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to load recent activity')
    }
  },
)

export const fetchDashboard = createAsyncThunk(
  'dashboard/fetchAll',
  async (_, { dispatch }) => {
    await Promise.all([
      dispatch(fetchDashboardStats()),
      dispatch(fetchRecentActivity())
    ]);
  }
)

const slice = createSlice({
  name: 'dashboard',
  initialState: { data: null, loading: false, error: null },
  reducers: {},
  extraReducers: (b) => {
    b.addCase(fetchDashboardStats.pending, (s) => { s.loading = true; s.error = null })
     .addCase(fetchDashboardStats.fulfilled, (s, a) => { 
        s.loading = false; 
        s.data = { ...s.data, ...a.payload };
      })
     .addCase(fetchDashboardStats.rejected, (s, a) => { s.loading = false; s.error = a.payload })
     .addCase(fetchRecentActivity.fulfilled, (s, a) => {
        s.data = { ...s.data, recent_activity: a.payload };
     })
  },
})

export default slice.reducer
