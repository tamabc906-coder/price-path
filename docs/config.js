// Cấu hình giao diện. VAPID_PUBLIC phải TRÙNG Secret VAPID_PUBLIC_KEY trên GitHub
// (sinh bằng venv\Scripts\python -m job.gen_vapid). Để trống = nút "Bật thông báo" bị khoá.
// WORKER_URL trống = điện thoại hiện đoạn mã đăng ký để dán vào Secret PUSH_SUBS_FALLBACK.
window.PP_CONFIG = {
  VAPID_PUBLIC: "BKovgXaJrzCbrYAEQLWnQl39OtVNzmw9ZqK-jRJhuL_7-Va0w6vd_qvB9aVcV6sdZ8g8fF2jDMSbWojcoqUkuzA",
  WORKER_URL: "",
};
