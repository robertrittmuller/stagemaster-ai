import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Download, Info, Zap, ShieldCheck, RefreshCw, Loader2 } from 'lucide-react';
import Header from '../components/Common/Header';
import RenderingProgress from '../components/Staging/RenderingProgress';
import BeforeAfterSlider from '../components/Results/BeforeAfterSlider';
import { getJobStatus, createStagingJob } from '../services/api';

const JobDetail = () => {
    const { jobId } = useParams();
    const navigate = useNavigate();
    const [job, setJob] = useState(null);
    const [error, setError] = useState(null);
    const [isRetrying, setIsRetrying] = useState(false);

    const handleRetry = async () => {
        if (!job) return;
        setIsRetrying(true);
        try {
            const newJob = await createStagingJob(
                job.image_id,
                job.room_type,
                job.style_preset,
                {
                    fixWhiteBalance: job.fix_white_balance,
                    wallDecorations: job.wall_decorations
                }
            );
            navigate(`/job/${newJob.id}`);
        } catch (e) {
            console.error("Retry failed:", e);
            alert("Failed to retry staging. Please try again.");
        } finally {
            setIsRetrying(false);
        }
    };

    useEffect(() => {
        setJob(null);
        setError(null);
        let interval;
        const fetchStatus = async () => {
            try {
                const data = await getJobStatus(jobId);
                setJob(data);
                if (data.status === 'completed' || data.status === 'error') {
                    clearInterval(interval);
                }
            } catch (e) {
                setError("Failed to load job details");
                clearInterval(interval);
            }
        };

        fetchStatus();
        interval = setInterval(fetchStatus, 3000);

        return () => clearInterval(interval);
    }, [jobId]);

    return (
        <div className="min-h-screen bg-surface-dim">
            <Header />
            <main className="max-w-6xl mx-auto px-6 py-10">
                {/* Back Link */}
                <div className="mb-8 animate-fade-in">
                    <Link
                        to="/gallery"
                        className="inline-flex items-center gap-2 text-on-surface-variant hover:text-accent font-medium text-sm transition-colors group"
                    >
                        <ArrowLeft size={16} className="transition-transform group-hover:-translate-x-1" />
                        Back to Gallery
                    </Link>
                </div>

                {/* Loading State */}
                {!job && !error && (
                    <div className="flex flex-col justify-center items-center h-[50vh] gap-4">
                        <Loader2 size={32} className="text-accent animate-spin" />
                        <p className="text-on-surface-variant font-medium">Loading...</p>
                    </div>
                )}

                {/* Error State */}
                {error && (
                    <div className="bg-surface border border-outline-variant p-10 rounded-2xl text-center max-w-md mx-auto shadow-elevation-2">
                        <div className="w-14 h-14 bg-error/10 text-error rounded-xl flex items-center justify-center mx-auto mb-5">
                            <Info size={28} />
                        </div>
                        <h2 className="text-xl font-semibold text-primary mb-2">Unable to Load</h2>
                        <p className="text-on-surface-variant mb-6">{error}</p>
                        <Link
                            to="/"
                            className="inline-block bg-primary text-white px-6 py-2.5 rounded-lg font-medium"
                        >
                            Return Home
                        </Link>
                    </div>
                )}

                {/* Job Content */}
                {job && (
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                        {/* Main Content */}
                        <div className="lg:col-span-8 animate-fade-in">
                            {job.status === 'completed' ? (
                                <BeforeAfterSlider
                                    original={job.original_image_url}
                                    staged={job.result_url}
                                />
                            ) : job.status === 'error' ? (
                                <div className="aspect-[4/3] bg-surface border border-outline-variant rounded-2xl flex flex-col items-center justify-center p-10 text-center">
                                    <div className="w-16 h-16 bg-error/10 text-error rounded-xl flex items-center justify-center mb-6">
                                        <RefreshCw size={32} />
                                    </div>
                                    <h2 className="text-2xl font-semibold text-primary mb-3">Processing Failed</h2>
                                    <p className="text-on-surface-variant max-w-sm mb-8">
                                        {job.error_message || "Something went wrong while processing your image."}
                                    </p>
                                    <button
                                        onClick={handleRetry}
                                        disabled={isRetrying}
                                        className="bg-accent hover:bg-accent-700 text-white px-6 py-3 rounded-xl font-semibold transition-all shadow-elevation-2 flex items-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
                                    >
                                        {isRetrying ? (
                                            <>
                                                <Loader2 size={18} className="animate-spin" />
                                                Retrying...
                                            </>
                                        ) : (
                                            "Try Again"
                                        )}
                                    </button>
                                </div>
                            ) : (
                                <div className="space-y-8">
                                    <RenderingProgress job={job} />
                                    <div className="relative w-full min-h-[200px] overflow-hidden rounded-2xl shadow-elevation-4 border border-outline-variant bg-surface-container">
                                        <img
                                            src={job.original_image_url}
                                            alt="Original"
                                            className="w-full h-auto block opacity-60"
                                        />
                                        <div className="absolute inset-0 flex items-center justify-center">
                                            <div className="bg-white/90 backdrop-blur-sm px-6 py-3 rounded-2xl flex items-center gap-3 shadow-elevation-3 border border-white/50">
                                                <Loader2 size={20} className="text-accent animate-spin" />
                                                <span className="text-base font-bold text-primary">AI is staging your room...</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Sidebar */}
                        <div className="lg:col-span-4 space-y-6 animate-slide-up">
                            {/* Metadata Card */}
                            <div className="bg-surface rounded-2xl p-6 shadow-elevation-2 border border-outline-variant">
                                <h3 className="text-base font-semibold text-primary mb-6 flex items-center gap-2">
                                    <Zap size={18} className="text-accent" />
                                    Job Details
                                </h3>

                                <div className="space-y-6">
                                    {/* Room & Style */}
                                    <div className="space-y-3">
                                        <div className="flex justify-between items-center py-2 px-3 bg-surface-container rounded-lg">
                                            <span className="text-sm text-on-surface-variant">Room Type</span>
                                            <span className="text-sm font-medium text-primary capitalize">{job.room_type.replace('_', ' ')}</span>
                                        </div>
                                        <div className="flex justify-between items-center py-2 px-3 bg-surface-container rounded-lg">
                                            <span className="text-sm text-on-surface-variant">Style</span>
                                            <span className="text-sm font-medium text-primary capitalize">{job.style_preset}</span>
                                        </div>
                                    </div>

                                    {/* Technical Info */}
                                    <div className="pt-4 border-t border-outline-variant space-y-2">
                                        <div className="flex justify-between items-center">
                                            <span className="text-xs text-on-surface-muted">Job ID</span>
                                            <span className="text-xs font-mono text-on-surface-variant">{job.id.substring(0, 12)}</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-xs text-on-surface-muted">Format</span>
                                            <span className="text-xs text-on-surface-variant">JPEG • HD</span>
                                        </div>
                                    </div>
                                </div>

                                {/* Download Button */}
                                {job.status === 'completed' && (
                                    <button
                                        onClick={async () => {
                                            try {
                                                const response = await fetch(job.result_url);
                                                const blob = await response.blob();
                                                const url = window.URL.createObjectURL(blob);
                                                const link = document.createElement('a');
                                                link.href = url;
                                                link.download = `staged-${job.id.substring(0, 8)}.jpg`;
                                                document.body.appendChild(link);
                                                link.click();
                                                document.body.removeChild(link);
                                                window.URL.revokeObjectURL(url);
                                            } catch (error) {
                                                console.error("Download failed:", error);
                                                alert("Failed to download image. Please try right-clicking the image and selecting 'Save Image As'.");
                                            }
                                        }}
                                        className="w-full mt-6 bg-primary hover:bg-primary-700 text-white py-3 rounded-xl font-semibold shadow-elevation-2 hover:shadow-elevation-3 transition-all flex items-center justify-center gap-2 active:scale-[0.98]"
                                    >
                                        <Download size={18} />
                                        Download Image
                                    </button>
                                )}
                            </div>

                            {/* Compliance Notice */}
                            <div className="p-5 bg-accent-50 border border-accent-200 rounded-xl flex gap-3">
                                <ShieldCheck size={20} className="text-accent shrink-0 mt-0.5" />
                                <div>
                                    <p className="text-sm font-medium text-accent-700 mb-1">MLS Compliant</p>
                                    <p className="text-xs text-accent-600 leading-relaxed">
                                        This image includes virtual staging disclosure metadata for compliance.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default JobDetail;
