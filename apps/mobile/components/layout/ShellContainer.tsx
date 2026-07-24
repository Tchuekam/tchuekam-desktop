import React from "react";
import { View, StyleSheet, StatusBar } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { primitives, radius } from "../../theme";

export interface ShellContainerProps {
  children: React.ReactNode;
}

export function ShellContainer({ children }: ShellContainerProps) {
  return (
    <View style={styles.outerCanvas}>
      <StatusBar barStyle="dark-content" backgroundColor={primitives.outerCanvas} />
      <SafeAreaView style={styles.phoneShell}>
        <View style={styles.contentArea}>{children}</View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  outerCanvas: {
    flex: 1,
    backgroundColor: primitives.outerCanvas,
  },
  phoneShell: {
    flex: 1,
    backgroundColor: primitives.phoneShell,
    borderTopLeftRadius: radius["3xl"],
    borderTopRightRadius: radius["3xl"],
    overflow: "hidden",
  },
  contentArea: {
    flex: 1,
  },
});
