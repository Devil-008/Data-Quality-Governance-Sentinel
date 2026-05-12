import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import api from '../../api/axios'

export const fetchRuleBooks = createAsyncThunk(
  'ruleBooks/list',
  async (_, { rejectWithValue }) => {
    try {
      const res = await api.get('/api/rule-books/list')
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to load rule books')
    }
  },
)

export const createRuleBook = createAsyncThunk(
  'ruleBooks/create',
  async ({ name, description, content, file, connector_type, dataset_type }, { rejectWithValue, dispatch }) => {
    try {
      const formData = new FormData()
      formData.append('name', name)
      if (description) formData.append('description', description)
      if (content) formData.append('rule_content', content)
      if (file) formData.append('file', file)
      if (connector_type) formData.append('connector_type', connector_type)
      if (dataset_type) formData.append('dataset_type', dataset_type)
      
      const res = await api.post('/api/rule-books/create', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      dispatch(fetchRuleBooks())
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to create rule book')
    }
  },
)

export const deleteRuleBook = createAsyncThunk(
  'ruleBooks/delete',
  async (id, { rejectWithValue, dispatch }) => {
    try {
      await api.delete(`/api/rule-books/${id}`)
      dispatch(fetchRuleBooks())
      return { id }
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to delete rule book')
    }
  },
)

export const searchSimilarRuleBooks = createAsyncThunk(
  'ruleBooks/search',
  async ({ id, topK }, { rejectWithValue }) => {
    try {
      const res = await api.get(`/api/rule-books/${id}/search-similar`, {
        params: { top_k: topK },
      })
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Search failed')
    }
  },
)

export const fetchRuleBookRules = createAsyncThunk(
  'ruleBooks/fetchRules',
  async (ruleBookId, { rejectWithValue }) => {
    try {
      const res = await api.get(`/api/rule-books/${ruleBookId}/rules`)
      return { ruleBookId, rules: res.data }
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to load rules')
    }
  },
)

export const addRuleToRuleBook = createAsyncThunk(
  'ruleBooks/addRule',
  async ({ ruleBookId, ruleName, ruleType, ruleConfig }, { rejectWithValue, dispatch }) => {
    try {
      const res = await api.post(`/api/rule-books/${ruleBookId}/rules`, null, {
        params: { rule_name: ruleName, rule_type: ruleType, rule_config: ruleConfig },
      })
      dispatch(fetchRuleBookRules(ruleBookId))
      return res.data
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to add rule')
    }
  },
)

export const deleteRuleFromRuleBook = createAsyncThunk(
  'ruleBooks/deleteRule',
  async ({ ruleBookId, ruleId }, { rejectWithValue, dispatch }) => {
    try {
      await api.delete(`/api/rule-books/${ruleBookId}/rules/${ruleId}`)
      dispatch(fetchRuleBookRules(ruleBookId))
      return { ruleId }
    } catch (e) {
      return rejectWithValue(e.response?.data?.detail || 'Failed to delete rule')
    }
  },
)

const slice = createSlice({
  name: 'ruleBooks',
  initialState: { 
    list: [], 
    loading: false, 
    error: null,
    searchResults: [],
    currentRuleBookRules: [],
  },
  reducers: {
    clearSearchResults(state) { state.searchResults = [] },
    clearError(state) { state.error = null },
    clearCurrentRules(state) { state.currentRuleBookRules = [] },
  },
  extraReducers: (b) => {
    b.addCase(fetchRuleBooks.pending, (s) => { s.loading = true; s.error = null })
     .addCase(fetchRuleBooks.fulfilled, (s, a) => { s.loading = false; s.list = a.payload })
     .addCase(fetchRuleBooks.rejected, (s, a) => { s.loading = false; s.error = a.payload })
     .addCase(searchSimilarRuleBooks.fulfilled, (s, a) => { s.searchResults = a.payload })
     .addCase(fetchRuleBookRules.fulfilled, (s, a) => { s.currentRuleBookRules = a.payload.rules })
  },
})

export const { clearSearchResults, clearError, clearCurrentRules } = slice.actions
export default slice.reducer
