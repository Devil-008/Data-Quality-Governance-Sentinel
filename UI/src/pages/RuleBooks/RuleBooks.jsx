import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Button, Card, CardContent, Stack, Chip, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem,
  Table, TableHead, TableRow, TableCell, TableBody, Paper, Alert, Tooltip,
  CircularProgress, Drawer, Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteIcon from '@mui/icons-material/Delete';
import SearchIcon from '@mui/icons-material/Search';
import CloseIcon from '@mui/icons-material/Close';
import DescriptionIcon from '@mui/icons-material/Description';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useDispatch, useSelector } from 'react-redux';
import {
  fetchRuleBooks, createRuleBook, deleteRuleBook, searchSimilarRuleBooks, clearSearchResults,
  fetchRuleBookRules, addRuleToRuleBook, deleteRuleFromRuleBook, clearCurrentRules,
} from '../../redux/slices/ruleBookSlice';
import Loader from '../../components/Loader';

const RULE_TYPES = [
  { value: 'null_check', label: 'Null Check' },
  { value: 'unique_check', label: 'Unique Check' },
  { value: 'range_check', label: 'Range Check' },
  { value: 'regex_check', label: 'Regex Check' },
  { value: 'custom_sql', label: 'Custom SQL' },
];

const CONNECTOR_TYPES = [
  { value: '', label: 'All Connectors' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'mssql', label: 'MSSQL' },
  { value: 'azure_adf', label: 'Azure Data Factory' },
  { value: 'databricks', label: 'Databricks' },
  { value: 'github', label: 'GitHub' },
];

const DATASET_TYPES = [
  { value: '', label: 'All Dataset Types' },
  { value: 'table', label: 'Table' },
  { value: 'view', label: 'View' },
  { value: 'job', label: 'Job' },
  { value: 'cluster', label: 'Cluster' },
  { value: 'pipeline', label: 'Pipeline' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'dataset', label: 'Dataset' },
];

const RuleBooks = () => {
  const dispatch = useDispatch();
  const { list, loading, error, searchResults, currentRuleBookRules } = useSelector((s) => s.ruleBooks);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [file, setFile] = useState(null);
  const [connectorType, setConnectorType] = useState('');
  const [datasetType, setDatasetType] = useState('');
  const [savingError, setSavingError] = useState(null);
  const [selectedRuleBook, setSelectedRuleBook] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searching, setSearching] = useState(null);
  const [addRuleDialogOpen, setAddRuleDialogOpen] = useState(false);
  const [newRuleName, setNewRuleName] = useState('');
  const [newRuleType, setNewRuleType] = useState('null_check');
  const [newRuleConfig, setNewRuleConfig] = useState('');

  useEffect(() => {
    dispatch(fetchRuleBooks());
  }, [dispatch]);

  const openRuleBook = (rb) => {
    setSelectedRuleBook(rb);
    setDrawerOpen(true);
    dispatch(clearSearchResults());
    dispatch(fetchRuleBookRules(rb.id));
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    setSelectedRuleBook(null);
    dispatch(clearSearchResults());
    dispatch(clearCurrentRules());
  };

  const openAddRuleDialog = () => {
    setNewRuleName('');
    setNewRuleType('null_check');
    setNewRuleConfig('');
    setAddRuleDialogOpen(true);
  };

  const closeAddRuleDialog = () => {
    setAddRuleDialogOpen(false);
  };

  const handleAddRule = async () => {
    if (!newRuleName || !newRuleConfig) return;
    await dispatch(addRuleToRuleBook({
      ruleBookId: selectedRuleBook.id,
      ruleName: newRuleName,
      ruleType: newRuleType,
      ruleConfig: newRuleConfig,
    }));
    closeAddRuleDialog();
  };

  const handleDeleteRule = async (ruleId) => {
    if (!window.confirm('Delete this rule?')) return;
    await dispatch(deleteRuleFromRuleBook({
      ruleBookId: selectedRuleBook.id,
      ruleId: ruleId,
    }));
  };

  const openDialog = () => {
    setName('');
    setDescription('');
    setContent('');
    setFile(null);
    setConnectorType('');
    setDatasetType('');
    setSavingError(null);
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
  };

  const handleSave = async () => {
    setSavingError(null);
    if (!name.trim()) {
      setSavingError('Rule book name is required');
      return;
    }
    if (!content && !file) {
      setSavingError('Either content or file is required');
      return;
    }
    const res = await dispatch(createRuleBook({ 
      name, 
      description, 
      content, 
      file,
      connector_type: connectorType || null,
      dataset_type: datasetType || null,
    }));
    if (createRuleBook.fulfilled.match(res)) {
      closeDialog();
    } else {
      setSavingError(res.payload || 'Failed to create rule book');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this rule book?')) return;
    await dispatch(deleteRuleBook(id));
  };

  const handleSearchSimilar = async (rb) => {
    setSearching(rb.id);
    await dispatch(searchSimilarRuleBooks({ id: rb.id, topK: 5 }));
    setSearching(null);
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>Rule Books</Typography>
        <Stack direction="row" spacing={1}>
          <Button startIcon={<RefreshIcon />} onClick={() => dispatch(fetchRuleBooks())} variant="outlined">
            Refresh
          </Button>
          <Button startIcon={<AddIcon />} onClick={openDialog} variant="contained">
            Add Rule Book
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Card>
        <CardContent>
          {loading && (!list || list.length === 0) ? (
            <Loader label="Loading rule books..." />
          ) : !list || list.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 6 }}>
              <Typography color="text.secondary">
                No rule books yet. Click "Add Rule Book" to create your first one.
              </Typography>
            </Box>
          ) : (
            <Paper variant="outlined" sx={{ boxShadow: 'none' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell><strong>Name</strong></TableCell>
                    <TableCell><strong>Connector Type</strong></TableCell>
                    <TableCell><strong>Dataset Type</strong></TableCell>
                    <TableCell><strong>Created At</strong></TableCell>
                    <TableCell align="right"><strong>Actions</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {list.map((rb) => (
                    <TableRow key={rb.id} hover onClick={() => openRuleBook(rb)} sx={{ cursor: 'pointer' }}>
                      <TableCell sx={{ fontWeight: 500 }}>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <DescriptionIcon fontSize="small" color="primary" />
                          {rb.name}
                        </Stack>
                      </TableCell>
                      <TableCell>
                        {rb.connector_type ? (
                          <Chip label={rb.connector_type} size="small" variant="outlined" />
                        ) : (
                          <Typography variant="caption" color="text.secondary">-</Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        {rb.dataset_type ? (
                          <Chip label={rb.dataset_type} size="small" variant="outlined" />
                        ) : (
                          <Typography variant="caption" color="text.secondary">-</Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption">
                          {rb.created_at ? new Date(rb.created_at).toLocaleString() : '-'}
                        </Typography>
                      </TableCell>
                      <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                        <Tooltip title="Search Similar">
                          <IconButton size="small" onClick={() => handleSearchSimilar(rb)} disabled={searching === rb.id}>
                            {searching === rb.id ? <CircularProgress size={16} /> : <SearchIcon fontSize="small" />}
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete">
                          <IconButton size="small" color="error" onClick={() => handleDelete(rb.id)}>
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="md" fullWidth>
        <DialogTitle>Add Rule Book</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {savingError && <Alert severity="error">{savingError}</Alert>}
            <TextField
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              fullWidth
              multiline
              rows={2}
            />
            <TextField
              select
              label="Connector Type"
              value={connectorType}
              onChange={(e) => setConnectorType(e.target.value)}
              fullWidth
            >
              {CONNECTOR_TYPES.map((t) => (
                <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Dataset Type"
              value={datasetType}
              onChange={(e) => setDatasetType(e.target.value)}
              fullWidth
            >
              {DATASET_TYPES.map((t) => (
                <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
              ))}
            </TextField>
            <TextField
              label="Rule Content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              fullWidth
              multiline
              rows={8}
            />
            <Box>
              <Typography variant="subtitle2">Or upload a file:</Typography>
              <input
                type="file"
                accept=".txt,.md,.json,.yaml,.yml"
                onChange={(e) => setFile(e.target.files[0] || null)}
                style={{ marginTop: 8 }}
              />
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button onClick={handleSave} variant="contained" disabled={loading}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer anchor="right" open={drawerOpen} onClose={closeDrawer} PaperProps={{ sx: { width: { xs: '100%', md: 800 } } }}>
        <Box sx={{ p: 3 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>{selectedRuleBook?.name}</Typography>
            <IconButton onClick={closeDrawer}><CloseIcon /></IconButton>
          </Stack>
          {selectedRuleBook ? (
            <Box>
              {selectedRuleBook.description && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  {selectedRuleBook.description}
                </Typography>
              )}
              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>Rule Content</Typography>
                  <Paper variant="outlined" sx={{ p: 2, fontFamily: 'monospace', fontSize: 14, maxHeight: '40vh', overflow: 'auto' }}>
                    <pre>{selectedRuleBook.rule_content}</pre>
                  </Paper>
                </CardContent>
              </Card>

              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Validation Rules</Typography>
                    <Button startIcon={<AddIcon />} onClick={openAddRuleDialog} variant="contained" size="small">
                      Add Rule
                    </Button>
                  </Stack>
                  {currentRuleBookRules.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No validation rules yet. Click "Add Rule" to create one.
                    </Typography>
                  ) : (
                    <Stack spacing={1}>
                      {currentRuleBookRules.map((rule) => (
                        <Accordion key={rule.id} disableGutters>
                          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                            <Stack direction="row" spacing={2} alignItems="center" sx={{ width: '100%' }}>
                              <Chip label={rule.rule_type} size="small" color="primary" />
                              <Typography variant="body2" sx={{ fontWeight: 500 }}>{rule.rule_name}</Typography>
                              <IconButton
                                size="small"
                                color="error"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteRule(rule.id);
                                }}
                                sx={{ ml: 'auto' }}
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </Stack>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Typography variant="caption" color="text.secondary">
                              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                {rule.rule_config}
                              </pre>
                            </Typography>
                          </AccordionDetails>
                        </Accordion>
                      ))}
                    </Stack>
                  )}
                </CardContent>
              </Card>

              {searchResults.length > 0 && (
                <>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>Similar Rule Books</Typography>
                  <Card variant="outlined" sx={{ mb: 2 }}>
                    <CardContent>
                      <Stack spacing={1}>
                        {searchResults.map((res, i) => (
                          <Chip
                            key={i}
                            label={`${res.name} (distance: ${res.distance.toFixed(2)})`}
                            color="primary"
                            variant="outlined"
                          />
                        ))}
                      </Stack>
                    </CardContent>
                  </Card>
                </>
              )}
            </Box>
          ) : (
            <Loader label="Loading..." />
          )}
        </Box>
      </Drawer>

      <Dialog open={addRuleDialogOpen} onClose={closeAddRuleDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Add Validation Rule</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Rule Name"
              value={newRuleName}
              onChange={(e) => setNewRuleName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              select
              label="Rule Type"
              value={newRuleType}
              onChange={(e) => setNewRuleType(e.target.value)}
              fullWidth
            >
              {RULE_TYPES.map((t) => (
                <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
              ))}
            </TextField>
            <TextField
              label="Rule Config (JSON)"
              value={newRuleConfig}
              onChange={(e) => setNewRuleConfig(e.target.value)}
              fullWidth
              multiline
              rows={4}
              placeholder={`{\n  "column": "id",\n  "max_nulls": 0\n}`}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeAddRuleDialog}>Cancel</Button>
          <Button onClick={handleAddRule} variant="contained">
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RuleBooks;
