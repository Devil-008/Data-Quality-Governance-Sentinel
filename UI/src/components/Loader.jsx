import { Box, CircularProgress, Typography } from '@mui/material'

export default function Loader({ label = 'Loading...' }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', py: 6 }}>
      <CircularProgress size={28} />
      <Typography variant="caption" sx={{ mt: 1.5, color: 'text.secondary' }}>{label}</Typography>
    </Box>
  )
}
