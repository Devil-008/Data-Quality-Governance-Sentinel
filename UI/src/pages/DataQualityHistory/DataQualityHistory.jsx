import React from 'react';
import { Box, Typography, Container, Paper } from '@mui/material';
import ConstructionIcon from '@mui/icons-material/Construction';

const DataQualityHistory = () => {
  return (
    <Container maxWidth="lg">
      <Box sx={{ mt: 4, mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 3 }}>
          Data Quality History
        </Typography>
        <Paper 
          sx={{ 
            p: 8, 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center',
            justifyContent: 'center',
            textAlign: 'center',
            borderRadius: 2,
            bgcolor: 'grey.50',
            border: '1px dashed',
            borderColor: 'divider'
          }}
        >
          <ConstructionIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h5" color="text.secondary" gutterBottom sx={{ fontWeight: 600 }}>
            Development in Progress
          </Typography>
          <Typography variant="body1" color="text.secondary">
            This module is currently under active development. 
            Stay tuned for a comprehensive history of your data quality metrics!
          </Typography>
        </Paper>
      </Box>
    </Container>
  );
};

export default DataQualityHistory;
