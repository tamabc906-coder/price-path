// Cấu hình giao diện. VAPID_PUBLIC phải TRÙNG Secret VAPID_PUBLIC_KEY trên GitHub
// (sinh bằng venv\Scripts\python -m job.gen_vapid). Để trống = nút "Bật thông báo" bị khoá.
// WORKER_URL trống = điện thoại hiện đoạn mã đăng ký để dán vào Secret PUSH_SUBS_FALLBACK.
window.PP_CONFIG = {
  VAPID_PUBLIC: "",
  WORKER_URL: "",
};
