import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

R_COLS = [
    "ricoverati_con_sintomi",
    "terapia_intensiva",
    "totale_ospedalizzati",
    "isolamento_domiciliare",
    "totale_positivi",
    "dimessi_guariti",
    "deceduti",
    "casi_da_sospetto_diagnostico",
    "casi_da_screening",
    "totale_casi",
]

R_COEFF = np.array(
    [
        [-1, -1, 1] + [0] * 7,
        [0] * 2 + [-1, -1, 1] + [0] * 5,
        [0] * 4 + [-1, -1, -1] + [0] * 2 + [1],
        [0] * 7 + [-1, -1, 1],
    ]
)
assert R_COEFF.ndim == 2
assert R_COEFF.shape[1] == len(R_COLS)
assert np.linalg.matrix_rank(R_COEFF) == len(R_COEFF)

R_COEFF_NZ = [c.nonzero()[0] for c in R_COEFF]

R_COLS_INV = [[R_COLS[j] for j in ind] for ind in R_COEFF_NZ]


def read_csv(pth):
    frame = None
    try:
        frame = pd.read_csv(
            pth,
            encoding="UTF-8",
            na_values=[""],
            keep_default_na=False,
            parse_dates=["data"],
        )
    except pd.errors.ParserError as exc:
        print(
            "\n* {}:\n  CSV PARSE ERROR: {}".format(
                pth,
                str(exc).strip(),
            ),
            file=sys.stderr,
        )

    return frame


def check_inv_regioni(df):
    data = df[R_COLS].to_numpy()
    if np.isnan(data).any():
        # nans in relevant data columns:
        # invariants are computed row by row to avoid nan propagation.
        # For IEEE754 0*nan is nan,
        # while here a 0 coeff. means ignore data altogether
        delta = []
        for ind, c in zip(R_COEFF_NZ, R_COEFF):
            delta.append(c[ind] @ data.T[ind])
        delta = np.array(delta)
    else:
        delta = R_COEFF @ data.T
    nz = delta.nonzero()
    return delta[nz], nz


def check_regioni(pth, regioni):

    delta, (invariant, ri) = check_inv_regioni(regioni)
    assert delta.shape == invariant.shape == ri.shape

    # na values means that check was not performed, due to missing data
    # here this condition is not reported
    notna = ~np.isnan(delta)
    delta, invariant, ri = delta[notna], invariant[notna], ri[notna]

    if len(delta) == 0:
        # nothing to report, return
        return 0

    # some error conditions to report
    print("\n* {}:".format(pth), file=sys.stderr)
    for i in range(len(R_COEFF)):
        pos = invariant == i
        if np.count_nonzero(pos) == 0:
            continue
        regs = ri[pos]
        wrong = regioni.loc[regs, ["denominazione_regione"] + R_COLS_INV[i]].copy()
        assert (wrong.index == regs).all()
        wrong["*DELTA*"] = delta[pos]
        print(
            "  INVARIANT[{}] ERROR on {} rows".format(i, len(wrong)),
            textwrap.indent(
                wrong.to_string(
                    index=False,
                ),
                "  | ",
            ),
            sep="\n",
            file=sys.stderr,
        )

    return len(delta)


def count_diff(a, b):
    if a.equals(b):
        return 0

    diff = 0

    pos = ~(a.isna() & b.isna())
    diff += (a[pos] != b[pos]).sum()

    return diff


def check_regioni_all(ref, df, pth):

    if ref.equals(df):
        return 0

    # here we have problems ...

    print("\n* {}: NOT EQUIVALENT TO DAILY FILES".format(pth), file=sys.stderr)

    # first check if dataframes are aligned

    if (ref.columns != df.columns).any():
        print("  Columns are not aligned", file=sys.stderr)
        return 1

    if len(ref) != len(df):
        print(
            "  Different number of rows: exptected {}, is {}".format(len(ref), len(df))
        )
        return 1

    assert ref.index.equals(df.index)

    errors = 0
    for c in ref:
        errors += (d := count_diff(ref[c], df[c]))
        if d > 0:
            print("  Column '{}': {} differences".format(c, d), file=sys.stderr)

    return errors


def main():

    # check dati-regioni daily files and consolidate them in dati_regioni
    dati_regioni = pd.DataFrame()
    errors = 0

    for pth in sorted(
        Path("dati-regioni").glob("dpc-covid19-ita-regioni-????????.csv")
    ):
        if (df := read_csv(pth)) is None:
            errors += 1
            continue
        errors += check_regioni(pth, df)
        dati_regioni = dati_regioni.append(df, ignore_index=True)

    pth = Path("dati-regioni") / "dpc-covid19-ita-regioni.csv"
    if (df := read_csv(pth)) is None:
        errors += 1
    else:
        errors += check_regioni_all(dati_regioni, df, pth)

    if errors:
        sys.exit("\nFound {:d} error(s)".format(errors))


if __name__ == "__main__":
    main()
