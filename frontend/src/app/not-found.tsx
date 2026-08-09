import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl py-20 text-center">
      <div className="text-sm font-medium text-accent">页面不存在</div>
      <h1 className="mt-3 text-2xl font-semibold">这个入口已经不可用</h1>
      <p className="mt-3 text-sm text-gray-400">
        正式功能已统一到首页、知识库、导入文件和问答页面。
      </p>
      <Link href="/" className="btn mt-6 inline-block">返回首页</Link>
    </div>
  );
}
