import React from "react";
import { Composition } from "remotion";
import { TeachXDemo } from "./TeachXDemo";
import { TeachXUsage } from "./TeachXUsage";
import { TEACHX_REAL_DURATION, TeachXReal } from "./TeachXReal";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TeachXDemo"
        component={TeachXDemo}
        durationInFrames={1110}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="TeachXUsage"
        component={TeachXUsage}
        durationInFrames={1950}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="TeachXReal"
        component={TeachXReal}
        durationInFrames={TEACHX_REAL_DURATION}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
