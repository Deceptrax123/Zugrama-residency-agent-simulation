declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    BUCKET?: R2Bucket;
    EXTRACTION_WORKER_TOKEN?: string;
    PROFILE_ADMIN_TOKEN?: string;
    RESIDENCY_BRIDGE_TOKEN?: string;
    RESIDENCY_HOST_TOKEN?: string;
  }
}
