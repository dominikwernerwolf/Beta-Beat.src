import sys
import os
from matcher_model_default import MatcherModelDefault
from matchers.kmod_matcher import KmodMatcher
from Python_Classes4MAD import metaclass


class MatcherModelKmod(MatcherModelDefault):

    def get_matcher_dict(self):
        matcher_dict = super(MatcherModelKmod, self).get_matcher_dict()
        matcher_dict["type"] = "kmod"
        return matcher_dict

    def create_matcher(self, match_path):
        self._matcher = KmodMatcher(self._name, self.get_matcher_dict(), match_path)

    def get_plotter(self, figures):
        return MatcherPlotterKmod(figures, self)


class MatcherPlotterKmod(object):

    def __init__(self, figures, matcher_model):
        assert type(matcher_model) is MatcherModelKmod
        self._figures = figures
        self._matcher_model = matcher_model

    def plot(self):
        if 1 in self._matcher_model._matcher.get_beams():
            figure_b1_x = self._figures[0][0]
            figure_b1_x.clear()
            kmod_bb_beam1_horizontal = self._get_kmod_beta_beat_file(1, "X")
            bb_beam1_horizontal = self._get_beta_beat_file(1, "X")
            self._plot_match(figure_b1_x, kmod_bb_beam1_horizontal, bb_beam1_horizontal, "X")

            figure_b1_y = self._figures[0][1]
            figure_b1_y.clear()
            kmod_bb_beam1_vertical = self._get_kmod_beta_beat_file(1, "Y")
            bb_beam1_vertical = self._get_beta_beat_file(1, "Y")
            self._plot_match(figure_b1_y, kmod_bb_beam1_vertical, bb_beam1_vertical, "Y")

        if 2 in self._matcher_model._matcher.get_beams():
            figure_b2_x = self._figures[1][0]
            figure_b2_x.clear()
            kmod_bb_beam2_horizontal = self._get_kmod_beta_beat_file(2, "X")
            bb_beam2_horizontal = self._get_beta_beat_file(2, "X")
            self._plot_match(figure_b2_x, kmod_bb_beam2_horizontal, bb_beam2_horizontal, "X")

            figure_b2_y = self._figures[1][1]
            figure_b2_y.clear()
            kmod_bb_beam2_vertical = self._get_kmod_beta_beat_file(2, "Y")
            bb_beam2_vertical = self._get_beta_beat_file(2, "Y")
            self._plot_match(figure_b2_y, kmod_bb_beam2_vertical, bb_beam2_vertical, "Y")

    def _get_kmod_beta_beat_file(self, beam, plane):
        kmod_bb_path = getattr(self._matcher_model, "get_beam" + str(beam) + "_output_path")()
        file_data = metaclass.twiss(os.path.join(
            kmod_bb_path, "sbs",
            "sbskmodbetabeat" + plane.lower() + "_IP" + str(self._matcher_model.get_ip()) + ".out")
        )
        return file_data

    def _get_beta_beat_file(self, beam, plane):
        bb_path = getattr(self._matcher_model, "get_beam" + str(beam) + "_output_path")()
        file_data = metaclass.twiss(os.path.join(
            bb_path, "sbs",
            "sbsbetabeat" + plane.lower() + "_IP" + str(self._matcher_model.get_ip()) + ".out")
        )
        return file_data

    def _plot_match(self, figure, kmod_bb_data, bb_data, plane):
        ax = figure.add_subplot(1, 1, 1)

        if self._matcher_model.get_propagation() == "front":
            MatcherPlotterKmod._plot_front(ax, kmod_bb_data, bb_data, plane)
        elif self._matcher_model.get_propagation() == "back":
            MatcherPlotterKmod._plot_back(ax, kmod_bb_data, bb_data, plane)

        ax.legend(loc="upper left", prop={'size': 16})
        ax.set_ylabel(r"$\Delta\beta/\beta_{model}$")
        ax.set_xlabel("S along the segment [m]")
        figure.patch.set_visible(False)
        figure.canvas.draw()

    @staticmethod
    def _plot_front(axes, kmod_bb_data, bb_data, plane):
        axes.plot(bb_data.S, getattr(bb_data, "BETABEATCOR" + plane),
                  label=r"$\Delta\beta/\beta_{model}$ model", color="green")
        axes.plot(bb_data.S, getattr(bb_data, "BETABEATCOR" + plane),
                  marker="o", markersize=7., color="green")

        axes.errorbar(kmod_bb_data.S,
                      getattr(kmod_bb_data, "BETABEAT" + plane),
                      getattr(kmod_bb_data, "ERRBETABEAT" + plane),
                      fmt='o', markersize=8., label=r"$\Delta\beta/\beta_{model}$ k-mod", color="blue")

    @staticmethod
    def _plot_back(axes, kmod_bb_data, bb_data, plane):
        axes.plot(bb_data.S, getattr(bb_data, "BETABEATCORBACK" + plane),
                  label=r"$\Delta\beta/\beta_{model}$ model", color="green")
        axes.plot(bb_data.S, getattr(bb_data, "BETABEATCORBACK" + plane),
                  marker="o", markersize=7., color="green")

        axes.errorbar(kmod_bb_data.S,
                      getattr(kmod_bb_data, "BETABEATBACK" + plane),
                      getattr(kmod_bb_data, "ERRBETABEATBACK" + plane),
                      fmt='o', markersize=8., label=r"$\Delta\beta/\beta_{model}$ k-mod", color="blue")


if __name__ == "__main__":
    print >> sys.stderr, "This module is meant to be imported."
    sys.exit(-1)