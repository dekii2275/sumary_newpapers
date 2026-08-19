export default function Home() {
  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "4rem 2rem",
        background: "#f8fafc",
        color: "#0f172a",
      }}
    >
      <section style={{ maxWidth: 800, margin: "0 auto" }}>
        <p style={{ color: "#4f46e5", fontWeight: 700 }}>AI TECH NEWS</p>
        <h1>News Intelligence Platform</h1>
        <p>
          Frontend scaffold đang chạy. Đây sẽ là giao diện tổng hợp, tóm tắt và
          hỏi đáp tin tức AI/công nghệ.
        </p>
        <p>
          Backend API: <code>http://localhost:18080</code>
        </p>
      </section>
    </main>
  );
}
