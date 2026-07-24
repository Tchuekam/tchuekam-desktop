import React from "react";
import { Tabs } from "expo-router";
import { primitives } from "../../theme";

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: primitives.phoneShell,
          borderTopColor: "rgba(31, 36, 29, 0.08)",
          height: 60,
          paddingBottom: 8,
        },
        tabBarActiveTintColor: primitives.accentBlack,
        tabBarInactiveTintColor: primitives.mutedSage,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Assistant",
        }}
      />
    </Tabs>
  );
}
