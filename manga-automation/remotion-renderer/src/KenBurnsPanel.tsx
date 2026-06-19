import React from "react";
import { AbsoluteFill, Img, useCurrentFrame, interpolate, Easing } from "remotion";

type MotionType = "zoom_center" | "pan_right" | "pan_up" | "pan_down";

interface KenBurnsPanelProps {
    imagePath: string;
    motionType: MotionType;
    durationInFrames: number;
}

export const KenBurnsPanel: React.FC<KenBurnsPanelProps> = ({
    imagePath,
    motionType,
    durationInFrames,
}) => {
    const frame = useCurrentFrame();

    const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
        extrapolateRight: "clamp",
    });

    let transform = "";

    switch (motionType) {
        case "zoom_center": {
            const scale = interpolate(progress, [0, 1], [1, 1.25], {
                easing: Easing.out(Easing.cubic),
            });
            transform = `scale(${scale})`;
            break;
        }

        case "pan_right": {
            const translateX = interpolate(progress, [0, 1], [0, -10], {
                easing: Easing.inOut(Easing.cubic),
            });
            transform = `scale(1.2) translateX(${translateX}%)`;
            break;
        }

        case "pan_up": {
            const translateY = interpolate(progress, [0, 1], [5, -5], {
                easing: Easing.inOut(Easing.cubic),
            });
            transform = `scale(1.2) translateY(${translateY}%)`;
            break;
        }

        case "pan_down": {
            const translateY = interpolate(progress, [0, 1], [-5, 5], {
                easing: Easing.inOut(Easing.cubic),
            });
            transform = `scale(1.2) translateY(${translateY}%)`;
            break;
        }

        default:
            transform = "scale(1)";
    }

    return (
        <AbsoluteFill
            style={{
                overflow: "hidden",
                backgroundColor: "#000",
            }}
        >
            <Img
                src={imagePath}
                style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    transform,
                    transformOrigin: "center center",
                    willChange: "transform",
                }}
            />
        </AbsoluteFill>
    );
};
