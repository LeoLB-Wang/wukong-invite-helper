#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>

static inline unsigned char ClampToByte(CGFloat value) {
    if (value < 0.0) {
        return 0;
    }
    if (value > 255.0) {
        return 255;
    }
    return (unsigned char)lrint(value);
}

static CGRect CropRectForMode(NSSize imageSize, NSString *mode) {
    CGFloat width = imageSize.width;
    CGFloat height = imageSize.height;

    if ([mode containsString:@"tight"]) {
        return CGRectMake(width * 0.20, height * 0.02, width * 0.46, height * 0.18);
    }
    if ([mode containsString:@"wide"]) {
        return CGRectMake(width * 0.12, height * 0.01, width * 0.62, height * 0.24);
    }
    return CGRectMake(width * 0.18, height * 0.02, width * 0.54, height * 0.20);
}

static void ModeParameters(NSString *mode, CGFloat *contrast, CGFloat *brightness, BOOL *invert, NSInteger *threshold) {
    *contrast = 2.6;
    *brightness = 18.0;
    *invert = NO;
    *threshold = -1;

    if ([mode isEqualToString:@"upper_soft"]) {
        *contrast = 1.8;
        *brightness = 26.0;
    } else if ([mode isEqualToString:@"upper_contrast"]) {
        *contrast = 3.4;
        *brightness = 8.0;
    } else if ([mode hasSuffix:@"240"]) {
        *threshold = 240;
    } else if ([mode hasSuffix:@"245"]) {
        *threshold = 245;
    } else if ([mode hasSuffix:@"250"]) {
        *threshold = 250;
    }
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 3) {
            fprintf(stderr, "usage: %s <input> <output> [mode]\n", argv[0]);
            return 2;
        }

        NSString *inputPath = [NSString stringWithUTF8String:argv[1]];
        NSString *outputPath = [NSString stringWithUTF8String:argv[2]];
        NSString *mode = argc >= 4 ? [NSString stringWithUTF8String:argv[3]] : @"upper_contrast";

        NSImage *image = [[NSImage alloc] initWithContentsOfFile:inputPath];
        if (!image) {
            fprintf(stderr, "failed to load image\n");
            return 1;
        }

        CGImageRef sourceImage = [image CGImageForProposedRect:NULL context:nil hints:nil];
        if (!sourceImage) {
            fprintf(stderr, "failed to decode image\n");
            return 1;
        }

        size_t sourceWidth = CGImageGetWidth(sourceImage);
        size_t sourceHeight = CGImageGetHeight(sourceImage);
        CGRect cropRect = CGRectIntegral(CropRectForMode(NSMakeSize(sourceWidth, sourceHeight), mode));
        CGImageRef croppedImage = CGImageCreateWithImageInRect(sourceImage, cropRect);
        if (!croppedImage) {
            fprintf(stderr, "failed to crop image\n");
            return 1;
        }

        NSBitmapImageRep *srcRep = [[NSBitmapImageRep alloc] initWithCGImage:croppedImage];
        CGImageRelease(croppedImage);
        if (!srcRep) {
            fprintf(stderr, "failed to create source bitmap\n");
            return 1;
        }

        NSInteger srcWidth = srcRep.pixelsWide;
        NSInteger srcHeight = srcRep.pixelsHigh;
        NSInteger threshold = -1;
        CGFloat contrast = 2.6;
        CGFloat brightness = 18.0;
        BOOL invert = NO;
        ModeParameters(mode, &contrast, &brightness, &invert, &threshold);
        NSInteger scale = threshold >= 0 ? 6 : 4;
        NSBitmapImageRep *dstRep = [[NSBitmapImageRep alloc]
            initWithBitmapDataPlanes:NULL
                          pixelsWide:srcWidth * scale
                          pixelsHigh:srcHeight * scale
                       bitsPerSample:8
                     samplesPerPixel:4
                            hasAlpha:YES
                            isPlanar:NO
                      colorSpaceName:NSCalibratedRGBColorSpace
                         bitmapFormat:0
                          bytesPerRow:0
                         bitsPerPixel:0];
        if (!dstRep) {
            fprintf(stderr, "failed to create destination bitmap\n");
            return 1;
        }

        for (NSInteger y = 0; y < srcHeight; y++) {
            for (NSInteger x = 0; x < srcWidth; x++) {
                NSColor *color = [srcRep colorAtX:x y:y];
                CGFloat red = color.redComponent * 255.0;
                CGFloat green = color.greenComponent * 255.0;
                CGFloat blue = color.blueComponent * 255.0;
                CGFloat alpha = color.alphaComponent * 255.0;

                CGFloat gray = (red * 0.299) + (green * 0.587) + (blue * 0.114);
                CGFloat adjusted = gray;
                if (threshold >= 0) {
                    adjusted = gray >= threshold ? 255.0 : 0.0;
                } else {
                    adjusted = ((gray - 128.0) * contrast) + 128.0 + brightness;
                    if (invert) {
                        adjusted = 255.0 - adjusted;
                    }
                }
                unsigned char finalGray = ClampToByte(adjusted);
                NSColor *outColor = [NSColor colorWithCalibratedRed:finalGray / 255.0
                                                              green:finalGray / 255.0
                                                               blue:finalGray / 255.0
                                                              alpha:alpha / 255.0];
                for (NSInteger dy = 0; dy < scale; dy++) {
                    for (NSInteger dx = 0; dx < scale; dx++) {
                        [dstRep setColor:outColor atX:(x * scale) + dx y:(y * scale) + dy];
                    }
                }
            }
        }

        NSData *pngData = [dstRep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
        if (!pngData || ![pngData writeToFile:outputPath atomically:YES]) {
            fprintf(stderr, "failed to write image\n");
            return 1;
        }
    }
    return 0;
}
