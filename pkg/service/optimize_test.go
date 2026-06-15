package service

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func postJSON(t *testing.T, a *Analyzer, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	a.router.ServeHTTP(w, req)
	return w
}

func TestOptimizeEndpointBaseline(t *testing.T) {
	gin.SetMode(gin.TestMode)
	a := NewAnalyzer()

	pd := ProblemData{
		MaxBatchSize: 256, MaxQueueSize: 128,
		AvgInputTokens: 256, AvgOutputTokens: 1024,
		Alpha: 8, Beta: 0.033, Gamma: 0.000333,
		TargetTTFT: 60, TargetITL: 20,
	}
	w := postJSON(t, a, "/optimize", pd)
	if w.Code != http.StatusOK {
		t.Fatalf("status got %d, want 200; body=%s", w.Code, w.Body.String())
	}
	var out OptimizeData
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if !out.Feasible {
		t.Error("baseline should be feasible")
	}
	if out.Concurrency < 1 || out.Concurrency > 256 {
		t.Errorf("concurrency %d out of [1,256]", out.Concurrency)
	}
	if out.Throughput <= 0 {
		t.Errorf("throughput should be > 0, got %v", out.Throughput)
	}
}

func TestOptimizeEndpointRejectsInvalid(t *testing.T) {
	gin.SetMode(gin.TestMode)
	a := NewAnalyzer()
	pd := ProblemData{MaxBatchSize: 0} // invalid: maxBatchSize must be > 0
	w := postJSON(t, a, "/optimize", pd)
	if w.Code != http.StatusBadRequest {
		t.Errorf("status got %d, want 400", w.Code)
	}
}
