// frontend/src/components/footer.jsx
function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="text-center text-muted py-3 border-top mt-5">
      <small>
        © {currentYear} Historical Stocks
      </small>
    </footer>
  );
}

export default Footer;
