def slugify(value, allow_unicode=False):
    import unicodedata
    import re

    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    source: https://github.com/django/django/blob/master/django/utils/text.py
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def multiply_unit_cell(cif, threshold):
    """Returns the multiplication factors (tuple of 3 int) for the cell vectors
    to respect, in every direction: min(perpendicular_width) > threshold
    """
    from math import cos, sin, sqrt, pi, fabs, ceil
    import numpy as np
    import six

    deg2rad = pi / 180.0

    # Parsing cif
    struct = next(six.itervalues(cif.values.dictionary))
    a = float(struct["_cell_length_a"])
    b = float(struct["_cell_length_b"])
    c = float(struct["_cell_length_c"])
    alpha = float(struct["_cell_angle_alpha"]) * deg2rad
    beta = float(struct["_cell_angle_beta"]) * deg2rad
    gamma = float(struct["_cell_angle_gamma"]) * deg2rad

    # Computing triangular cell matrix
    v = sqrt(
        1
        - cos(alpha) ** 2
        - cos(beta) ** 2
        - cos(gamma) ** 2
        + 2 * cos(alpha) * cos(beta) * cos(gamma)
    )
    cell = np.zeros((3, 3))
    cell[0, :] = [a, 0, 0]
    cell[1, :] = [b * cos(gamma), b * sin(gamma), 0]
    cell[2, :] = [
        c * cos(beta),
        c * (cos(alpha) - cos(beta) * cos(gamma)) / (sin(gamma)),
        c * v / sin(gamma),
    ]
    cell = np.array(cell)

    axc1 = cell[0, 0] * cell[2, 2]
    axc2 = -cell[0, 0] * cell[2, 1]
    bxc1 = cell[1, 1] * cell[2, 2]
    bxc2 = -cell[1, 0] * cell[2, 2]
    bxc3 = cell[1, 0] * cell[2, 1] - cell[1, 1] * cell[2, 0]
    det = fabs(cell[0, 0] * cell[1, 1] * cell[2, 2])
    perpwidth = np.zeros(3)
    perpwidth[0] = det / sqrt(bxc1 ** 2 + bxc2 ** 2 + bxc3 ** 2)
    perpwidth[1] = det / sqrt(axc1 ** 2 + axc2 ** 2)
    perpwidth[2] = cell[2, 2]

    return tuple(int(ceil(threshold / perpwidth[i])) for i in range(3))
