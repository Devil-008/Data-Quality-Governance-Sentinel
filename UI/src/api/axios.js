import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://127.0.0.1:3008",
  timeout: 120000,
});
// http://122.163.121.176:3008
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response && err.response.status === 401) {
      const path = window.location.pathname
      if (path !== '/login') {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  },
)

export default api
