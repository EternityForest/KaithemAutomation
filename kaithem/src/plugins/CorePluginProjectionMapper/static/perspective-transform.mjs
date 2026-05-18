/**
 * Perspective Transform - ES Module wrapper around numeric.js
 * Computes perspective transformation matrix for 4-point mapping
 */

import numeric from 'numeric';

/**
 * Calculate perspective transformation coefficients
 */
function getNormalizationCoefficients(sourcePoints, destinationPoints, isInverse) {
  if (isInverse) {
    const temporary = destinationPoints;
    destinationPoints = sourcePoints;
    sourcePoints = temporary;
  }

  // Build system matrix
  const matA = [
    [sourcePoints[0], sourcePoints[1], 1, 0, 0, 0, -1*destinationPoints[0]*sourcePoints[0], -1*destinationPoints[0]*sourcePoints[1]],
    [0, 0, 0, sourcePoints[0], sourcePoints[1], 1, -1*destinationPoints[1]*sourcePoints[0], -1*destinationPoints[1]*sourcePoints[1]],
    [sourcePoints[2], sourcePoints[3], 1, 0, 0, 0, -1*destinationPoints[2]*sourcePoints[2], -1*destinationPoints[2]*sourcePoints[3]],
    [0, 0, 0, sourcePoints[2], sourcePoints[3], 1, -1*destinationPoints[3]*sourcePoints[2], -1*destinationPoints[3]*sourcePoints[3]],
    [sourcePoints[4], sourcePoints[5], 1, 0, 0, 0, -1*destinationPoints[4]*sourcePoints[4], -1*destinationPoints[4]*sourcePoints[5]],
    [0, 0, 0, sourcePoints[4], sourcePoints[5], 1, -1*destinationPoints[5]*sourcePoints[4], -1*destinationPoints[5]*sourcePoints[5]],
    [sourcePoints[6], sourcePoints[7], 1, 0, 0, 0, -1*destinationPoints[6]*sourcePoints[6], -1*destinationPoints[6]*sourcePoints[7]],
    [0, 0, 0, sourcePoints[6], sourcePoints[7], 1, -1*destinationPoints[7]*sourcePoints[6], -1*destinationPoints[7]*sourcePoints[7]],
  ];

  const matB = destinationPoints;

  try {
    const matAT = numeric.transpose(matA);
    const matATA = numeric.dotMMsmall(matAT, matA);
    const matC = numeric.inv(matATA);
    const matD = numeric.dotMMsmall(matC, matAT);
    const matX = numeric.dotMV(matD, matB);

    for (let i = 0; i < matX.length; i++) {
      matX[i] = Math.round(matX[i] * 10_000_000_000) / 10_000_000_000;
    }
    matX[8] = 1;

    return matX;
  } catch (error) {
    console.error("Perspective transform error:", error);
    return [1, 0, 0, 0, 1, 0, 0, 0, 1];
  }
}

/**
 * Perspective Transform Class
 */
export class PerspT {
  constructor(sourcePoints, destinationPoints) {
    this.srcPts = sourcePoints;
    this.dstPts = destinationPoints;
    this.coeffs = getNormalizationCoefficients(this.srcPts, this.dstPts, false);
    this.coeffsInv = getNormalizationCoefficients(this.srcPts, this.dstPts, true);
  }

  transform(x, y) {
    const divisor = this.coeffs[6] * x + this.coeffs[7] * y + 1;
    return [
      (this.coeffs[0] * x + this.coeffs[1] * y + this.coeffs[2]) / divisor,
      (this.coeffs[3] * x + this.coeffs[4] * y + this.coeffs[5]) / divisor,
    ];
  }

  transformInverse(x, y) {
    const divisor = this.coeffsInv[6] * x + this.coeffsInv[7] * y + 1;
    return [
      (this.coeffsInv[0] * x + this.coeffsInv[1] * y + this.coeffsInv[2]) / divisor,
      (this.coeffsInv[3] * x + this.coeffsInv[4] * y + this.coeffsInv[5]) / divisor,
    ];
  }
}

export default PerspT;
