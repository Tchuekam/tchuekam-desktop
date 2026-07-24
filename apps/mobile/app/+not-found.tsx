import React from "react";
import { View, StyleSheet } from "react-native";
import { Link, Stack } from "expo-router";
import { ShellContainer } from "../components/layout/ShellContainer";
import { Typography } from "../components/ui/Typography";

export default function NotFoundScreen() {
  return (
    <ShellContainer>
      <Stack.Screen options={{ title: "Oops!" }} />
      <View style={styles.container}>
        <Typography variant="h1">This screen doesn't exist.</Typography>
        <Link href="/" style={styles.link}>
          <Typography variant="button" color="#2563eb">
            Go to home screen!
          </Typography>
        </Link>
      </View>
    </ShellContainer>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  },
  link: {
    marginTop: 15,
    paddingVertical: 15,
  },
});
