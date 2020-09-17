import codecs
import copy
import cv2
import numpy as np
from shapely import geometry as shgeo
from dotadev.misc import dota_utils as util
from pathlib import Path


def choose_best_pointorder_fit_another(poly1, poly2):
    """
    To make the two polygons best fit with each point
    """
    x1 = poly1[0]
    y1 = poly1[1]
    x2 = poly1[2]
    y2 = poly1[3]
    x3 = poly1[4]
    y3 = poly1[5]
    x4 = poly1[6]
    y4 = poly1[7]
    candidates = [
        np.array([x1, y1, x2, y2, x3, y3, x4, y4]),
        np.array([x2, y2, x3, y3, x4, y4, x1, y1]),
        np.array([x3, y3, x4, y4, x1, y1, x2, y2]),
        np.array([x4, y4, x1, y1, x2, y2, x3, y3]),
    ]
    dst_coordinate = np.array(poly2)
    distances = np.array([np.sum((coord - dst_coordinate) ** 2) for coord in candidates])
    sorted = distances.argsort()
    return candidates[sorted[0]]


def calchalf_iou(poly1, poly2):
    """
    It is not the iou on usual, the iou is the value of intersection over poly1
    """
    inter_poly = poly1.intersection(poly2)
    inter_area = inter_poly.area
    poly1_area = poly1.area
    half_iou = inter_area / poly1_area
    return inter_poly, half_iou


# point: (x, y), rec: (xmin, ymin, xmax, ymax)
# def __del__(self):
#     self.f_sub.close()
# grid --> (x, y) position of grids
def polyorig2sub(left, up, poly):
    polyInsub = np.zeros(len(poly))
    for i in range(int(len(poly) / 2)):
        polyInsub[i * 2] = int(poly[i * 2] - left)
        polyInsub[i * 2 + 1] = int(poly[i * 2 + 1] - up)
    return polyInsub


class DataSplitter:
    def __init__(
        self,
        basepath,
        outpath,
        code="utf-8",
        gap=100,
        subsize=1024,
        thresh=0.7,
        choosebestpoint=True,
        ext=".png",
    ):
        """
        :param basepath: base path for dota data
        :param outpath: output base path for dota data,
        the basepath and outputpath have the similar subdirectory, 'images' and 'labelTxt'
        :param code: encoding format of txt file
        :param gap: overlap between two patches
        :param subsize: subsize of patch
        :param thresh: the thresh determine whether to keep the instance if the instance is cut down in the process of split
        :param choosebestpoint: used to choose the first point for the
        :param ext: ext for the image format
        """
        self.code = code
        self.gap = gap
        self.subsize = subsize
        self.slide = self.subsize - self.gap
        self.thresh = thresh
        self.imagepath = Path(basepath) / "images"
        self.labelpath = Path(basepath) / "labelTxt"
        self.outimagepath = Path(outpath) / "images"
        self.outlabelpath = Path(outpath) / "labelTxt"
        self.choosebestpoint = choosebestpoint
        self.ext = ext
        if not self.outimagepath.exists():
            self.outimagepath.mkdir(parents=True)
        if not self.outlabelpath.exists():
            self.outlabelpath.mkdir()

    def saveimagepatches(self, img, subimgname, left, up):
        subimg = copy.deepcopy(img[up : (up + self.subsize), left : (left + self.subsize)])
        outdir = self.outimagepath / (subimgname + self.ext)
        cv2.imwrite(str(outdir), subimg)

    def savepatches(self, resizeimg, objects, subimgname, left, up, right, down):
        outdir = self.outlabelpath / (subimgname + ".txt")
        # mask_poly = []
        imgpoly = shgeo.Polygon([(left, up), (right, up), (right, down), (left, down)])
        with codecs.open(outdir, "w", self.code) as f_out:
            for obj in objects:
                gtpoly = shgeo.Polygon(
                    [
                        (obj["poly"][0], obj["poly"][1]),
                        (obj["poly"][2], obj["poly"][3]),
                        (obj["poly"][4], obj["poly"][5]),
                        (obj["poly"][6], obj["poly"][7]),
                    ]
                )
                if gtpoly.area <= 0:
                    continue
                inter_poly, half_iou = calchalf_iou(gtpoly, imgpoly)

                # print('writing...')
                if half_iou == 1:
                    polyInsub = polyorig2sub(left, up, obj["poly"])
                    outline = " ".join(list(map(str, polyInsub)))
                    outline = outline + " " + obj["name"] + " " + str(obj["difficult"])
                    f_out.write(outline + "\n")
                elif half_iou > 0:
                    # elif (half_iou > self.thresh):
                    #  print('<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
                    inter_poly = shgeo.polygon.orient(inter_poly, sign=1)
                    out_poly = list(inter_poly.exterior.coords)[0:-1]
                    if len(out_poly) < 4:
                        continue

                    out_poly2 = []
                    for i in range(len(out_poly)):
                        out_poly2.append(out_poly[i][0])
                        out_poly2.append(out_poly[i][1])

                    if len(out_poly) == 5:
                        # print('==========================')
                        out_poly2 = util.poly5Topoly4(out_poly2)
                    elif len(out_poly) > 5:
                        """
                        if the cut instance is a polygon with points more than 5, we do not handle it currently
                        """
                        continue
                    if self.choosebestpoint:
                        out_poly2 = choose_best_pointorder_fit_another(out_poly2, obj["poly"])

                    polyInsub = polyorig2sub(left, up, out_poly2)

                    for index, item in enumerate(polyInsub):
                        if item <= 1:
                            polyInsub[index] = 1
                        elif item >= self.subsize:
                            polyInsub[index] = self.subsize
                    outline = " ".join(list(map(str, polyInsub)))
                    if half_iou > self.thresh:
                        outline = outline + " " + obj["name"] + " " + str(obj["difficult"])
                    else:
                        # if the left part is too small, label as '2'
                        outline = outline + " " + obj["name"] + " " + "2"
                    f_out.write(outline + "\n")
                # else:
                #   mask_poly.append(inter_poly)
        self.saveimagepatches(resizeimg, subimgname, left, up)

    def split_single(self, name, scale, ext):
        """
            split a single image and ground truth
        :param name: image name
        :param scale: the resize scale for the image
        :param ext: the image extension
        :return:
        """
        img = cv2.imread(str(self.imagepath / (name + ext)))
        if np.shape(img) == ():
            return
        fullname = self.labelpath / (name + ".txt")
        objects = util.parse_dota_poly2(fullname)
        for obj in objects:
            obj["poly"] = list(map(lambda x: scale * x, obj["poly"]))
            # obj['poly'] = list(map(lambda x: ([2 * y for y in x]), obj['poly']))

        if scale != 1:
            resizeimg = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        else:
            resizeimg = img
        outbasename = name + "__" + str(scale) + "__"
        weight = np.shape(resizeimg)[1]
        height = np.shape(resizeimg)[0]

        left, up = 0, 0
        while left < weight:
            if left + self.subsize >= weight:
                left = max(weight - self.subsize, 0)
            up = 0
            while up < height:
                if up + self.subsize >= height:
                    up = max(height - self.subsize, 0)
                right = min(left + self.subsize, weight - 1)
                down = min(up + self.subsize, height - 1)
                subimgname = outbasename + str(left) + "___" + str(up)
                # self.f_sub.write(name + ' ' + subimgname + ' ' + str(left) + ' ' + str(up) + '\n')
                self.savepatches(resizeimg, objects, subimgname, left, up, right, down)
                if up + self.subsize >= height:
                    break
                else:
                    up = up + self.slide
            if left + self.subsize >= weight:
                break
            else:
                left = left + self.slide

    def splitdata(self, scale):
        imagenames = [im.stem for im in self.imagepath.iterdir()]
        for name in imagenames:
            self.split_single(name, scale, self.ext)


if __name__ == "__main__":
    # example usage of ImgSplit
    split = DataSplitter(
        r"/home/ashwin/Desktop/Projects/DOTA_devkit/example",
        r"/home/ashwin/Desktop/Projects/DOTA_devkit/examplesplit",
    )
    split.splitdata(1)
