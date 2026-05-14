import React, { useEffect, useState } from 'react';
import {
    Box, Container, Typography, Button, Grid, Card, CardContent, Stack, Chip,
} from '@mui/material';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { useSelector } from 'react-redux';
import ShieldIcon from '@mui/icons-material/Shield';
import HubIcon from '@mui/icons-material/Hub';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import PsychologyIcon from '@mui/icons-material/Psychology';
import PrivacyTipIcon from '@mui/icons-material/PrivacyTip';
import InsightsIcon from '@mui/icons-material/Insights';
import RuleIcon from '@mui/icons-material/Rule';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import StorageIcon from '@mui/icons-material/Storage';
import CloudIcon from '@mui/icons-material/Cloud';
import DataObjectIcon from '@mui/icons-material/DataObject';
import LoginDialog from '../../components/LoginDialog';

const features = [
    {
        icon: <HubIcon sx={{ fontSize: 36 }} />,
        title: 'Universal Connectors',
        desc: 'One-click integration with MySQL, MSSQL, Azure Data Factory, Databricks pipelines and GitHub.',
        color: '#2563eb',
    },
    {
        icon: <MonitorHeartIcon sx={{ fontSize: 36 }} />,
        title: 'Deterministic Quality Engine',
        desc: 'Python-driven statistics for outliers, anomalies, governance, blank/garbage values and trend deviations.',
        color: '#16a34a',
    },
    {
        icon: <PsychologyIcon sx={{ fontSize: 36 }} />,
        title: 'AI Interpretation Layer',
        desc: 'Mistral-powered confidence scoring and natural-language interpretation on top of deterministic findings.',
        color: '#7c3aed',
    },
    {
        icon: <PrivacyTipIcon sx={{ fontSize: 36 }} />,
        title: 'PII & Governance',
        desc: 'Automatic detection of email, phone, Aadhaar, PAN and other sensitive categories across every dataset.',
        color: '#dc2626',
    },
    {
        icon: <InsightsIcon sx={{ fontSize: 36 }} />,
        title: 'Schema Drift Detection',
        desc: 'Continuous comparison of schema snapshots — column adds, drops and type changes raise smart alerts.',
        color: '#0891b2',
    },
    {
        icon: <RuleIcon sx={{ fontSize: 36 }} />,
        title: 'Rule Books & RAG',
        desc: 'Plug your own validation rule books — indexed in ChromaDB and consulted during quality runs.',
        color: '#d97706',
    },
];

const connectors = [
    { label: 'MySQL', icon: <StorageIcon /> },
    { label: 'MSSQL', icon: <StorageIcon /> },
    { label: 'Azure ADF', icon: <CloudIcon /> },
    { label: 'Databricks', icon: <DataObjectIcon /> },
    { label: 'GitHub', icon: <DataObjectIcon /> },
];

const Landing = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const [searchParams] = useSearchParams();
    const token = useSelector((s) => s.auth.token);
    const [loginOpen, setLoginOpen] = useState(false);

    const loginRequested = searchParams.get('login') === '1';

    const clearLoginQuery = () => {
        if (!searchParams.has('login') && !searchParams.has('from')) return;
        const next = new URLSearchParams(searchParams);
        next.delete('login');
        next.delete('from');
        const nextSearch = next.toString();
        navigate(
            { pathname: location.pathname, search: nextSearch ? `?${nextSearch}` : '' },
            { replace: true },
        );
    };

    const openLogin = () => {
        try { sessionStorage.removeItem('postLoginRedirect'); } catch { /* ignore */ }
        setLoginOpen(true);
    };

    const closeLogin = () => {
        setLoginOpen(false);
        clearLoginQuery();
    };

    const goPrimary = () => {
        if (token) navigate('/dashboard');
        else openLogin();
    };

    useEffect(() => {
        if (!token && loginRequested) {
            setLoginOpen(true);
        }
    }, [token, loginRequested]);

    const resolvePostLoginRedirect = () => {
        try {
            const stored = sessionStorage.getItem('postLoginRedirect');
            if (stored && stored !== '/' && !stored.startsWith('/login')) return stored;
        } catch {
            // ignore
        }
        return '/dashboard';
    };

    const handleLoginSuccess = () => {
        const target = resolvePostLoginRedirect();
        try { sessionStorage.removeItem('postLoginRedirect'); } catch { /* ignore */ }
        setLoginOpen(false);
        clearLoginQuery();
        navigate(target, { replace: true });
    };

    return (
        <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
            {/* Top nav */}
            <Box
                sx={{
                    position: 'sticky', top: 0, zIndex: 10,
                    bgcolor: 'background.paper',
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                }}
            >
                <Container maxWidth="lg">
                    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ py: 1.5 }}>
                        <Stack direction="row" alignItems="center" spacing={1}>
                            <ShieldIcon sx={{ color: 'primary.main' }} />
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>DQ Sentinel</Typography>
                        </Stack>
                        <Stack direction="row" spacing={1}>
                            <Button variant="text" onClick={openLogin}>
                                Sign in
                            </Button>
                            <Button variant="contained" onClick={goPrimary} endIcon={<ArrowForwardIcon />}>
                                {token ? 'Open Dashboard' : 'Get Started'}
                            </Button>
                        </Stack>
                    </Stack>
                </Container>
            </Box>

            {/* Hero */}
            <Box
                sx={{
                    background:
                        'linear-gradient(135deg, rgba(37,99,235,0.08) 0%, rgba(124,58,237,0.08) 100%)',
                    py: { xs: 8, md: 12 },
                }}
            >
                <Container maxWidth="lg">
                    <Grid container spacing={4} alignItems="center">
                        <Grid item xs={12} md={7}>
                            <Chip label="AI-Powered Data Observability" color="primary" variant="outlined" sx={{ mb: 2 }} />
                            <Typography variant="h2" sx={{ fontWeight: 800, lineHeight: 1.15, mb: 2, fontSize: { xs: 36, md: 52 } }}>
                                Trust your data.<br />
                                <Box component="span" sx={{ color: 'primary.main' }}>Catch issues before they hit production.</Box>
                            </Typography>
                            <Typography variant="h6" color="text.secondary" sx={{ fontWeight: 400, mb: 4, maxWidth: 640 }}>
                                DQ Sentinel watches every connector, every dataset and every pipeline.
                                Deterministic Python checks compute the score; Mistral AI interprets the findings.
                                You get the truth, with reasoning.
                            </Typography>
                            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                                <Button
                                    variant="contained" size="large"
                                    endIcon={<ArrowForwardIcon />}
                                    onClick={goPrimary}
                                    sx={{ px: 4, py: 1.5, fontSize: 16 }}
                                >
                                    {token ? 'Open Dashboard' : 'Start monitoring'}
                                </Button>
                                <Button
                                    variant="outlined" size="large"
                                    onClick={() => {
                                        const el = document.getElementById('features');
                                        if (el) el.scrollIntoView({ behavior: 'smooth' });
                                    }}
                                    sx={{ px: 4, py: 1.5, fontSize: 16 }}
                                >
                                    Explore features
                                </Button>
                            </Stack>
                        </Grid>
                        <Grid item xs={12} md={5}>
                            <Card sx={{ p: 1, borderRadius: 4, boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
                                <CardContent>
                                    <Typography variant="overline" color="text.secondary">Live Quality Score</Typography>
                                    <Stack direction="row" alignItems="baseline" spacing={1} sx={{ mb: 2 }}>
                                        <Typography variant="h2" sx={{ fontWeight: 800, color: 'success.main' }}>92.4</Typography>
                                        <Typography variant="h5" color="text.secondary">/100</Typography>
                                    </Stack>
                                    <Stack spacing={1.5}>
                                        {[
                                            { label: 'Completeness', val: 96, color: 'success.main' },
                                            { label: 'Uniqueness', val: 91, color: 'success.main' },
                                            { label: 'Accuracy', val: 88, color: 'warning.main' },
                                            { label: 'Governance', val: 94, color: 'success.main' },
                                            { label: 'Anomaly', val: 86, color: 'warning.main' },
                                        ].map((b) => (
                                            <Box key={b.label}>
                                                <Stack direction="row" justifyContent="space-between">
                                                    <Typography variant="caption" sx={{ fontWeight: 600 }}>{b.label}</Typography>
                                                    <Typography variant="caption">{b.val}/100</Typography>
                                                </Stack>
                                                <Box sx={{ height: 6, bgcolor: 'action.hover', borderRadius: 3 }}>
                                                    <Box sx={{ height: 6, bgcolor: b.color, borderRadius: 3, width: `${b.val}%` }} />
                                                </Box>
                                            </Box>
                                        ))}
                                    </Stack>
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>
                                        Confidence: 0.91 · Severity: low · 17/19 rules passed
                                    </Typography>
                                </CardContent>
                            </Card>
                        </Grid>
                    </Grid>
                </Container>
            </Box>

            {/* Stats strip */}
            <Container maxWidth="lg" sx={{ py: 4 }}>
                <Grid container spacing={3}>
                    {[
                        { val: '19+', label: 'Quality checks per dataset' },
                        { val: '5', label: 'Connector integrations' },
                        { val: '9', label: 'Rule categories' },
                        { val: '<1s', label: 'Avg confidence rating' },
                    ].map((s) => (
                        <Grid item xs={6} md={3} key={s.label}>
                            <Box sx={{ textAlign: 'center' }}>
                                <Typography variant="h3" sx={{ fontWeight: 800, color: 'primary.main' }}>{s.val}</Typography>
                                <Typography variant="body2" color="text.secondary">{s.label}</Typography>
                            </Box>
                        </Grid>
                    ))}
                </Grid>
            </Container>

            {/* Features */}
            <Box id="features" sx={{ py: { xs: 6, md: 10 }, bgcolor: 'background.paper' }}>
                <Container maxWidth="lg">
                    <Stack alignItems="center" sx={{ mb: 6 }}>
                        <Chip label="Capabilities" color="primary" variant="outlined" sx={{ mb: 1 }} />
                        <Typography variant="h3" sx={{ fontWeight: 800, textAlign: 'center', mb: 1 }}>
                            Everything you need to govern data
                        </Typography>
                        <Typography variant="h6" color="text.secondary" sx={{ fontWeight: 400, textAlign: 'center', maxWidth: 720 }}>
                            From discovery to alerting, DQ Sentinel covers the full data-quality lifecycle.
                        </Typography>
                    </Stack>
                    <Grid container spacing={3}>
                        {features.map((f) => (
                            <Grid item xs={12} sm={6} md={4} key={f.title}>
                                <Card sx={{ height: '100%', borderRadius: 3, transition: 'all .2s', '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 } }}>
                                    <CardContent sx={{ p: 3 }}>
                                        <Box sx={{ width: 56, height: 56, borderRadius: 2, bgcolor: `${f.color}15`, color: f.color, display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
                                            {f.icon}
                                        </Box>
                                        <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>{f.title}</Typography>
                                        <Typography variant="body2" color="text.secondary">{f.desc}</Typography>
                                    </CardContent>
                                </Card>
                            </Grid>
                        ))}
                    </Grid>
                </Container>
            </Box>

            {/* Connectors */}
            <Container maxWidth="lg" sx={{ py: { xs: 6, md: 10 } }}>
                <Stack alignItems="center" sx={{ mb: 4 }}>
                    <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>Plug into your stack</Typography>
                    <Typography variant="body1" color="text.secondary">Works with the tools your data team already uses</Typography>
                </Stack>
                <Grid container spacing={2} justifyContent="center">
                    {connectors.map((c) => (
                        <Grid item key={c.label}>
                            <Chip
                                icon={c.icon}
                                label={c.label}
                                sx={{
                                    px: 2, py: 3, fontSize: 16, fontWeight: 600,
                                    '& .MuiChip-icon': { color: 'primary.main' },
                                }}
                                variant="outlined"
                            />
                        </Grid>
                    ))}
                </Grid>
            </Container>

            {/* CTA */}
            <Box sx={{ py: { xs: 6, md: 10 }, background: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)' }}>
                <Container maxWidth="md">
                    <Stack alignItems="center" spacing={3}>
                        <Typography variant="h3" sx={{ color: 'white', fontWeight: 800, textAlign: 'center' }}>
                            Ready to put your data on autopilot?
                        </Typography>
                        <Typography variant="h6" sx={{ color: 'rgba(255,255,255,0.85)', fontWeight: 400, textAlign: 'center', maxWidth: 560 }}>
                            Sign in and connect your first source in under two minutes.
                        </Typography>
                        <Button
                            variant="contained" size="large" color="inherit"
                            onClick={goPrimary} endIcon={<ArrowForwardIcon />}
                            sx={{ bgcolor: 'white', color: 'primary.main', px: 4, py: 1.5, fontSize: 16, '&:hover': { bgcolor: '#f1f5f9' } }}
                        >
                            {token ? 'Open Dashboard' : 'Sign in to continue'}
                        </Button>
                    </Stack>
                </Container>
            </Box>

            <LoginDialog
                open={loginOpen}
                onClose={closeLogin}
                onSuccess={handleLoginSuccess}
            />

            {/* Footer */}
            <Box sx={{ py: 4, borderTop: '1px solid', borderColor: 'divider', bgcolor: 'background.paper' }}>
                <Container maxWidth="lg">
                    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems="center" spacing={2}>
                        <Stack direction="row" alignItems="center" spacing={1}>
                            <ShieldIcon sx={{ color: 'primary.main', fontSize: 20 }} />
                            <Typography variant="body2" color="text.secondary">
                                DQ Sentinel · AI-powered data quality, governance &amp; observability
                            </Typography>
                        </Stack>
                        <Typography variant="caption" color="text.secondary">
                            © {new Date().getFullYear()} DQ Sentinel
                        </Typography>
                    </Stack>
                </Container>
            </Box>
        </Box>
    );
};

export default Landing;
