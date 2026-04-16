/**
 * Perspective Transform - ES Module wrapper around numeric.js
 * Computes perspective transformation matrix for 4-point mapping
 */

import numeric from 'numeric';

/**
 * Calculate perspective transformation coefficients
 */
function getNormalizationCoefficients(sourcePts, dstPts, isInverse) {
  if (isInverse) {
    const temporary = dstPts;
    dstPts = sourcePts;
    sourcePts = temporary;
  }

  // Build system matrix
  const matA = [
    [sourcePts[0], sourcePts[1], 1, 0, 0, 0, -1*dstPts[0]*sourcePts[0], -1*dstPts[0]*sourcePts[1]],
    [0, 0, 0, sourcePts[0], sourcePts[1], 1, -1*dstPts[1]*sourcePts[0], -1*dstPts[1]*sourcePts[1]],
    [sourcePts[2], sourcePts[3], 1, 0, 0, 0, -1*dstPts[2]*sourcePts[2], -1*dstPts[2]*sourcePts[3]],
    [0, 0, 0, sourcePts[2], sourcePts[3], 1, -1*dstPts[3]*sourcePts[2], -1*dstPts[3]*sourcePts[3]],
    [sourcePts[4], sourcePts[5], 1, 0, 0, 0, -1*dstPts[4]*sourcePts[4], -1*dstPts[4]*sourcePts[5]],
    [0, 0, 0, sourcePts[4], sourcePts[5], 1, -1*dstPts[5]*sourcePts[4], -1*dstPts[5]*sourcePts[5]],
    [sourcePts[6], sourcePts[7], 1, 0, 0, 0, -1*dstPts[6]*sourcePts[6], -1*dstPts[6]*sourcePts[7]],
    [0, 0, 0, sourcePts[6], sourcePts[7], 1, -1*dstPts[7]*sourcePts[6], -1*dstPts[7]*sourcePts[7]],
  ];

  const matB = dstPts;

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
  constructor(sourcePts, dstPts) {
    this.srcPts = sourcePts;
    this.dstPts = dstPts;
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
