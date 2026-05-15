import React, { useEffect } from 'react';
import { 
  Box, Typography, Container, Paper, Table, TableBody, 
  TableCell, TableContainer, TableHead, TableRow, Chip,
  IconButton, Tooltip
} from '@mui/material';
import { useDispatch, useSelector } from 'react-redux';
import { fetchRuns } from '../../redux/slices/monitoringSlice';
import RefreshIcon from '@mui/icons-material/Refresh';
import Loader from '../../components/Loader';
import { format } from 'date-fns';

const DataQualityHistory = () => {
  const dispatch = useDispatch();
  const { runs, loading } = useSelector((s) => s.monitoring);

  useEffect(() => {
    dispatch(fetchRuns(50));
  }, [dispatch]);

  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'success': return 'success';
      case 'failed': return 'error';
      case 'running': return 'primary';
      default: return 'default';
    }
  };

  return (
    <Container maxWidth="lg">
      <Box sx={{ mt: 4, mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" sx={{ fontWeight: 700 }}>
            Data Quality History
          </Typography>
          <Tooltip title="Refresh">
            <IconButton onClick={() => dispatch(fetchRuns(50))} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>

        {loading && runs.length === 0 ? (
          <Loader label="Loading history..." />
        ) : (
          <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
            <Table>
              <TableHead sx={{ bgcolor: 'grey.50' }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Run ID</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Type</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Connector</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Started At</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Finished At</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {runs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
                      <Typography color="text.secondary">No monitoring runs found.</Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  runs.map((run) => (
                    <TableRow key={run.id} hover>
                      <TableCell>#{run.id}</TableCell>
                      <TableCell>
                        <Chip 
                          label={run.run_type?.toUpperCase() || 'UNKNOWN'} 
                          size="small" 
                          variant="outlined"
                          sx={{ fontWeight: 600, fontSize: '0.7rem' }}
                        />
                      </TableCell>
                      <TableCell>{run.connector_name || '-'}</TableCell>
                      <TableCell>
                        <Chip 
                          label={run.status || 'UNKNOWN'} 
                          size="small" 
                          color={getStatusColor(run.status)}
                          sx={{ fontWeight: 600, minWidth: 80 }}
                        />
                      </TableCell>
                      <TableCell>
                        {run.started_at ? format(new Date(run.started_at), 'MMM dd, yyyy HH:mm') : '-'}
                      </TableCell>
                      <TableCell>
                        {run.finished_at ? format(new Date(run.finished_at), 'MMM dd, yyyy HH:mm') : '-'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Box>
    </Container>
  );
};

export default DataQualityHistory;
