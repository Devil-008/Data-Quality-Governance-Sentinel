import { createSlice } from '@reduxjs/toolkit'

const stored = localStorage.getItem('theme_mode')
const initialMode = stored === 'dark' || stored === 'light' ? stored : 'light'

const slice = createSlice({
  name: 'theme',
  initialState: { mode: initialMode },
  reducers: {
    toggleTheme(state) {
      state.mode = state.mode === 'dark' ? 'light' : 'dark'
      localStorage.setItem('theme_mode', state.mode)
    },
    setTheme(state, action) {
      state.mode = action.payload
      localStorage.setItem('theme_mode', state.mode)
    },
  },
})

export const { toggleTheme, setTheme } = slice.actions
export default slice.reducer
