import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="standard-page not-found-page">
      <span className="error-code">404</span>
      <h1>页面不存在</h1>
      <p>链接可能已失效，或地址输入有误。</p>
      <Link className="primary-button" to="/">
        <ArrowLeft aria-hidden="true" size={17} />
        返回问答
      </Link>
    </div>
  );
}
