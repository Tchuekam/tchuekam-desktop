import React from "react";
import { View, ScrollView, StyleSheet } from "react-native";
import { ShellContainer } from "../../components/layout/ShellContainer";
import { Typography } from "../../components/ui/Typography";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { primitives, spacing } from "../../theme";

export default function AssistantScreen() {
  return (
    <ShellContainer>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header Badge & Title */}
        <View style={styles.headerRow}>
          <Badge variant="success">☀️ Yang Fire Day</Badge>
          <Badge variant="glow">v1.0.0 Enterprise</Badge>
        </View>

        <Typography variant="hero" style={styles.title}>
          What are you deciding right now?
        </Typography>

        <Typography variant="body" color={primitives.mutedSage} style={styles.subtitle}>
          Select a scenario to let TchueKAM AI align cosmic & technical attributes with your situation.
        </Typography>

        {/* Hero Recommendation Card Preview */}
        <Card variant="elevated" style={styles.heroCard}>
          <View style={styles.cardHeader}>
            <Badge variant="glow">AI ANALYSIS</Badge>
            <Badge variant="default">87 Score</Badge>
          </View>

          <View style={styles.checkBadge}>
            <Typography variant="title" color={primitives.pureWhite}>✓</Typography>
          </View>

          <Typography variant="h1" style={styles.cardHeading}>
            Recommended
          </Typography>

          <Typography variant="body" color={primitives.mutedSage} style={styles.cardBody}>
            The energies favor action. Your TchueKAM AI engine indicates strong fire & execution support for your goal today.
          </Typography>

          <View style={styles.metricsRow}>
            <View style={styles.metricCell}>
              <Typography variant="label">TIMING</Typography>
              <Typography variant="title" color="#2b5e3b">Good</Typography>
            </View>
            <View style={styles.metricCell}>
              <Typography variant="label">HARMONY</Typography>
              <Typography variant="title" color={primitives.deepCharcoal}>High</Typography>
            </View>
            <View style={styles.metricCell}>
              <Typography variant="label">RISK</Typography>
              <Typography variant="title" color={primitives.terracotta}>Low</Typography>
            </View>
          </View>
        </Card>

        {/* Action Controls */}
        <View style={styles.actionRow}>
          <Button variant="primary" style={styles.primaryButton}>
            Execute Scenario →
          </Button>
        </View>
      </ScrollView>
    </ShellContainer>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    padding: spacing[20],
    gap: spacing[16],
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  title: {
    marginTop: spacing[8],
  },
  subtitle: {
    marginBottom: spacing[8],
  },
  heroCard: {
    gap: spacing[12],
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  checkBadge: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: primitives.accentBlack,
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "center",
    marginVertical: spacing[8],
  },
  cardHeading: {
    textAlign: "center",
  },
  cardBody: {
    textAlign: "center",
    lineHeight: 22,
  },
  metricsRow: {
    flexDirection: "row",
    justifyContent: "space-around",
    borderTopWidth: 1,
    borderTopColor: "rgba(31, 36, 29, 0.08)",
    paddingTop: spacing[12],
    marginTop: spacing[8],
  },
  metricCell: {
    alignItems: "center",
    gap: 4,
  },
  actionRow: {
    marginTop: spacing[12],
  },
  primaryButton: {
    width: "100%",
  },
});
