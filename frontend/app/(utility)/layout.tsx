import UtilitySidebar from "@/components/sidebar/UtilitySidebar";
import AppShell from "@/components/layout/AppShell";
import { CapabilityAccessProvider } from "@/components/access/CapabilityAccessContext";
import CapabilityGate from "@/components/access/CapabilityGate";
import { OnboardingGate } from "@/components/auth/OnboardingGate";

export default function UtilityLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <OnboardingGate>
      <CapabilityAccessProvider>
        <AppShell sidebar={<UtilitySidebar />}>
          <CapabilityGate>{children}</CapabilityGate>
        </AppShell>
      </CapabilityAccessProvider>
    </OnboardingGate>
  );
}
