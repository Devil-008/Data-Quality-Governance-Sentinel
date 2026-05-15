import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Stack,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Paper,
  Alert,
  Tooltip,
  CircularProgress,
  Drawer,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteIcon from "@mui/icons-material/Delete";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import DescriptionIcon from "@mui/icons-material/Description";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchRuleBooks,
  createRuleBook,
  deleteRuleBook,
  searchSimilarRuleBooks,
  clearSearchResults,
  fetchRuleBookRules,
  addRuleToRuleBook,
  deleteRuleFromRuleBook,
  clearCurrentRules,
  fetchRuleBookDetails,
} from "../../redux/slices/ruleBookSlice";
import Loader from "../../components/Loader";

const RULE_TYPES = [
  { value: "null_check", label: "Null Check" },
  { value: "unique_check", label: "Unique Check" },
  { value: "range_check", label: "Range Check" },
  { value: "regex_check", label: "Regex Check" },
  { value: "custom_sql", label: "Custom SQL" },
];

const CONNECTOR_TYPES = [
  { value: "", label: "All Connectors" },
  { value: "mysql", label: "MySQL" },
  { value: "mssql", label: "MSSQL" },
  { value: "azure_adf", label: "Azure Data Factory" },
  { value: "databricks", label: "Databricks" },
  { value: "github", label: "GitHub" },
];

const DATASET_TYPES = [
  { value: "", label: "All Dataset Types" },
  { value: "table", label: "Table" },
  { value: "view", label: "View" },
  { value: "job", label: "Job" },
  { value: "cluster", label: "Cluster" },
  { value: "pipeline", label: "Pipeline" },
  { value: "workflow", label: "Workflow" },
  { value: "dataset", label: "Dataset" },
];

const RuleBooks = () => {
  const dispatch = useDispatch();
  const {
    list,
    loading,
    error,
    searchResults,
    currentRuleBookRules,
    selectedRuleBook: reduxSelectedRuleBook,
    selectedRuleBookLoading,
  } = useSelector((s) => s.ruleBooks);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState(null);
  const [connectorType, setConnectorType] = useState("");
  const [savingError, setSavingError] = useState(null);
  const [selectedRuleBook, setSelectedRuleBook] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searching, setSearching] = useState(null);
  const [addRuleDialogOpen, setAddRuleDialogOpen] = useState(false);
  const [newRuleName, setNewRuleName] = useState("");
  const [newRuleType, setNewRuleType] = useState("null_check");
  const [newRuleConfig, setNewRuleConfig] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = React.useRef(null);

  useEffect(() => {
    dispatch(fetchRuleBooks());
  }, [dispatch]);

  const openRuleBook = (rb) => {
    setSelectedRuleBook(rb);
    setDrawerOpen(true);
    dispatch(clearSearchResults());
    dispatch(fetchRuleBookRules(rb.id));
    dispatch(fetchRuleBookDetails(rb.id));
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    setSelectedRuleBook(null);
    dispatch(clearSearchResults());
    dispatch(clearCurrentRules());
  };

  const openAddRuleDialog = () => {
    setNewRuleName("");
    setNewRuleType("null_check");
    setNewRuleConfig("");
    setAddRuleDialogOpen(true);
  };

  const closeAddRuleDialog = () => {
    setAddRuleDialogOpen(false);
  };

  const handleAddRule = async () => {
    if (!newRuleName || !newRuleConfig) return;
    await dispatch(
      addRuleToRuleBook({
        ruleBookId: selectedRuleBook.id,
        ruleName: newRuleName,
        ruleType: newRuleType,
        ruleConfig: newRuleConfig,
      }),
    );
    closeAddRuleDialog();
  };

  const handleDeleteRule = async (ruleId) => {
    if (!window.confirm("Delete this rule?")) return;
    await dispatch(
      deleteRuleFromRuleBook({
        ruleBookId: selectedRuleBook.id,
        ruleId: ruleId,
      }),
    );
  };

  const openDialog = () => {
    setFile(null);
    setSavingError(null);
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
  };

  const handleSave = async () => {
    setSavingError(null);
    if (!file) {
      setSavingError("File is required");
      return;
    }
    setUploading(true);
    const res = await dispatch(
      createRuleBook({
        file,
        connectorType,
      }),
    );
    setUploading(false);
    if (createRuleBook.fulfilled.match(res)) {
      closeDialog();
    } else {
      setSavingError(res.payload || "Failed to create rule book");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this rule book?")) return;
    await dispatch(deleteRuleBook(id));
  };

  const handleSearchSimilar = async (rb) => {
    setSearching(rb.id);
    await dispatch(searchSimilarRuleBooks({ id: rb.id, topK: 5 }));
    setSearching(null);
  };

  const handleFileSelect = (selectedFile) => {
    if (selectedFile) {
      if (!selectedFile.name.endsWith(".txt")) {
        setSavingError("Only .txt files are allowed");
        setFile(null);
        return;
      }
      setFile(selectedFile);
      setSavingError(null);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleFileInputChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelect(e.target.files[0]);
    }
  };

  return (
    <Box>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 3 }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Rule Books
        </Typography>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Search"
            size="small"
            sx={{ flex: 1, maxWidth: 200 }}
          />
          <Button
            startIcon={<AddIcon />}
            onClick={openDialog}
            variant="contained"
          >
            Add Rule Book
          </Button>
          <Button
            startIcon={<RefreshIcon />}
            onClick={() => dispatch(fetchRuleBooks())}
            variant="outlined"
          ></Button>
        </Stack>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Card>
        <CardContent>
          {loading && (!list || list.length === 0) ? (
            <Loader label="Loading rule books..." />
          ) : !list || list.length === 0 ? (
            <Box sx={{ textAlign: "center", py: 6 }}>
              <Typography color="text.secondary">
                No rule books yet. Click "Add Rule Book" to create your first
                one.
              </Typography>
            </Box>
          ) : (
            <Paper variant="outlined" sx={{ boxShadow: "none" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>
                      <strong>Name</strong>
                    </TableCell>
                    <TableCell>
                      <strong>Connector Type</strong>
                    </TableCell>
                    <TableCell>
                      <strong>Created At</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Actions</strong>
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {list.map((rb) => (
                    <TableRow
                      key={rb.id}
                      hover
                      onClick={() => openRuleBook(rb)}
                      sx={{ cursor: "pointer" }}
                    >
                      <TableCell sx={{ fontWeight: 500 }}>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <DescriptionIcon fontSize="small" color="primary" />
                          {rb.rulebook_name || rb.name}
                        </Stack>
                      </TableCell>
                      <TableCell>
                        {rb.connector_type ? (
                          <Chip
                            label={rb.connector_type}
                            size="small"
                            variant="outlined"
                          />
                        ) : (
                          <Typography variant="caption" color="text.secondary">
                            -
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption">
                          {rb.created_at
                            ? new Date(rb.created_at).toLocaleString()
                            : "-"}
                        </Typography>
                      </TableCell>
                      <TableCell
                        align="right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Tooltip title="Delete">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => handleDelete(rb.id)}
                          >
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

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Upload Rule Book</DialogTitle>
        <DialogContent dividers>
          {uploading ? (
            <Box
              sx={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                minHeight: 300,
              }}
            >
              <Loader label="Uploading rule book..." />
            </Box>
          ) : (
            <Stack spacing={2} sx={{ mt: 1 }}>
              {savingError && <Alert severity="error">{savingError}</Alert>}

              {/* Connector Type Selection */}
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                  Connector Type (Optional)
                </Typography>
                <TextField
                  select
                  fullWidth
                  size="small"
                  value={connectorType}
                  onChange={(e) => setConnectorType(e.target.value)}
                  placeholder="Auto-detect if omitted"
                >
                  <MenuItem value="">
                    <em>Auto-detect</em>
                  </MenuItem>
                  <MenuItem value="MYSQL">MySQL</MenuItem>
                  <MenuItem value="MSSQL">MSSQL</MenuItem>
                  <MenuItem value="ADF">Azure Data Factory (ADF)</MenuItem>
                  <MenuItem value="DATABRICKS">Databricks</MenuItem>
                  <MenuItem value="GITHUB">GitHub</MenuItem>
                </TextField>
                <Typography variant="caption" color="text.secondary">
                  If omitted, the system will try to auto-detect the connector type from the file content.
                </Typography>
              </Box>

              {/* File Upload with Drag & Drop */}
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                  Upload Rule Book File (.txt only)
                </Typography>
                <Box
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                  sx={{
                    border: "2px dashed",
                    borderColor: dragActive ? "primary.main" : "divider",
                    borderRadius: 2,
                    p: 3,
                    textAlign: "center",
                    cursor: "pointer",
                    transition: "all 0.3s ease",
                    backgroundColor: dragActive
                      ? "action.hover"
                      : "action.disabledBackground",
                    "&:hover": {
                      borderColor: "primary.main",
                      backgroundColor: "action.hover",
                    },
                  }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".txt"
                    onChange={handleFileInputChange}
                    style={{ display: "none" }}
                  />

                  {file ? (
                    <Stack alignItems="center" spacing={1}>
                      <CheckCircleIcon
                        sx={{ fontSize: 40, color: "success.main" }}
                      />
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {file.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {(file.size / 1024).toFixed(2)} KB
                      </Typography>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={(e) => {
                          e.stopPropagation();
                          setFile(null);
                        }}
                        sx={{ mt: 1 }}
                      >
                        Remove File
                      </Button>
                    </Stack>
                  ) : (
                    <Stack alignItems="center" spacing={1}>
                      <CloudUploadIcon
                        sx={{ fontSize: 40, color: "primary.main" }}
                      />
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        Drag & drop your .txt file here
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        or click to browse
                      </Typography>
                    </Stack>
                  )}
                </Box>
              </Box>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={uploading}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            variant="contained"
            disabled={uploading || !file}
          >
            Upload
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={closeDrawer}
        PaperProps={{ sx: { width: { xs: "100%", md: 600 } } }}
      >
        <Box sx={{ p: 3 }}>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 3 }}
          >
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              Rule Book Details
            </Typography>
            <IconButton onClick={closeDrawer}>
              <CloseIcon />
            </IconButton>
          </Stack>
          {selectedRuleBook ? (
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  Rule Book Name
                </Typography>
                <Typography variant="body2">
                  {selectedRuleBook.rulebook_name}
                </Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  Connector Type
                </Typography>
                <Typography variant="body2">
                  {selectedRuleBook.connector_type || "-"}
                </Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  Created
                </Typography>
                <Typography variant="body2">
                  {selectedRuleBook.created_at
                    ? new Date(
                        selectedRuleBook.created_at,
                      ).toLocaleString()
                    : "-"}
                </Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  Content
                </Typography>
                <Paper
                  variant="outlined"
                  sx={{
                    p: 2,
                    backgroundColor: "#f5f5f5",
                    maxHeight: 500,
                    overflow: "auto",
                  }}
                >
                  <Typography
                    variant="body2"
                    sx={{
                      whiteSpace: "pre-wrap",
                      fontFamily: "monospace",
                      fontSize: "0.85rem",
                    }}
                  >
                    {selectedRuleBook.rulebook_content || "No content"}
                  </Typography>
                </Paper>
              </Box>
            </Stack>
          ) : (
            <Typography color="text.secondary">
              No rule book selected
            </Typography>
          )}
        </Box>
      </Drawer>

      <Dialog
        open={addRuleDialogOpen}
        onClose={closeAddRuleDialog}
        maxWidth="sm"
        fullWidth
      >
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
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
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
