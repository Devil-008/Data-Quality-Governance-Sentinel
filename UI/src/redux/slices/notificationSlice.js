import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import api from '../../api/axios'

export const fetchNotifications = createAsyncThunk('notifs/list', async () => {
  const res = await api.get('/api/notifications/list')
  return res.data
})

export const fetchUnreadCount = createAsyncThunk('notifs/unread', async () => {
  const res = await api.get('/api/notifications/unread-count')
  return res.data.count || 0
})

export const markRead = createAsyncThunk('notifs/markRead', async (id) => {
  await api.post(`/api/notifications/${id}/read`)
  return id
})

export const markAllRead = createAsyncThunk('notifs/markAll', async () => {
  await api.post('/api/notifications/read-all')
})

const slice = createSlice({
  name: 'notifications',
  initialState: { list: [], unread: 0 },
  reducers: {},
  extraReducers: (b) => {
    b.addCase(fetchNotifications.fulfilled, (s, a) => { s.list = a.payload })
     .addCase(fetchUnreadCount.fulfilled, (s, a) => { s.unread = a.payload })
     .addCase(markRead.fulfilled, (s, a) => {
        const n = s.list.find((x) => x.id === a.payload)
        if (n) n.is_read = 1
        s.unread = Math.max(0, s.unread - 1)
     })
     .addCase(markAllRead.fulfilled, (s) => {
        s.list = s.list.map((n) => ({ ...n, is_read: 1 }))
        s.unread = 0
     })
  },
})

export default slice.reducer
