import React from "react";
import { Composition } from "remotion";
import { TeachXDemo } from "./TeachXDemo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="TeachXDemo"
      component={TeachXDemo}
      durationInFrames={1110}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
