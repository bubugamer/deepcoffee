'use client'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 聊天气泡内的 Markdown 渲染：只用于 AI 输出（用户消息保持纯文本）。
// react-markdown 编译成 React 元素树、忽略内联 HTML，无需额外 sanitize。
export function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="space-y-2 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _n, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" className="text-dc-accent hover:underline" />
          ),
          ul: ({ node: _n, ...props }) => <ul {...props} className="list-disc pl-5 space-y-1" />,
          ol: ({ node: _n, ...props }) => <ol {...props} className="list-decimal pl-5 space-y-1" />,
          strong: ({ node: _n, ...props }) => <strong {...props} className="font-semibold text-dc-text-1" />,
          code: ({ node: _n, ...props }) => (
            <code {...props} className="bg-dc-subtle px-1 py-0.5 rounded text-[0.85em] break-words" />
          ),
          pre: ({ node: _n, ...props }) => (
            <pre {...props} className="bg-dc-subtle rounded-lg p-3 overflow-x-auto text-xs [&_code]:bg-transparent [&_code]:p-0" />
          ),
          blockquote: ({ node: _n, ...props }) => (
            <blockquote {...props} className="border-l-2 border-dc-border pl-3 text-dc-text-3" />
          ),
          table: ({ node: _n, ...props }) => (
            <div className="overflow-x-auto">
              <table {...props} className="text-xs border-collapse w-full" />
            </div>
          ),
          th: ({ node: _n, ...props }) => (
            <th {...props} className="border border-dc-border bg-dc-subtle px-2 py-1 text-left font-medium" />
          ),
          td: ({ node: _n, ...props }) => <td {...props} className="border border-dc-border px-2 py-1" />,
          hr: ({ node: _n, ...props }) => <hr {...props} className="border-dc-border" />,
          // 气泡里降级标题层级：LLM 输出的 #/## 渲染成加粗段落，避免撑爆气泡
          h1: ({ node: _n, ...props }) => <p {...props} className="font-semibold text-dc-text-1" />,
          h2: ({ node: _n, ...props }) => <p {...props} className="font-semibold text-dc-text-1" />,
          h3: ({ node: _n, ...props }) => <p {...props} className="font-semibold text-dc-text-1" />,
          h4: ({ node: _n, ...props }) => <p {...props} className="font-semibold text-dc-text-1" />,
        }}
      >
        {text}
      </Markdown>
    </div>
  )
}
