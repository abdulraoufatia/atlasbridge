import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <Card>
        <CardContent className="p-8 text-center space-y-4">
          <p className="text-4xl font-semibold text-muted-foreground">404</p>
          <p className="text-sm text-muted-foreground">This page does not exist</p>
          <Link href="/">
            <Button variant="secondary" size="sm" data-testid="button-go-home">
              <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to Overview
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
