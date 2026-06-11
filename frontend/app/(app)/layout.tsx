import AppLayout from '@/components/AppLayout'

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return <AppLayout>{children}</AppLayout>
}
